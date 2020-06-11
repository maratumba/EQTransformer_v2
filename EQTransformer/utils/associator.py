#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec 27 18:52:42 2019

@author: mostafamousavi

last update: 06/05/2020
"""

from datetime import datetime, timedelta
from tqdm import tqdm
import numpy as np
import json
import os
import sqlite3 
import pandas as pd
import csv
from os import listdir
import h5py
#import matplotlib.pyplot as plt
from obspy import UTCDateTime
from obspy.signal.trigger import ar_pick
from obspy.signal.trigger import recursive_sta_lta, trigger_onset
from itertools import combinations


def run_associator(input_dir,
                   preprocessed_dir, 
                   start_time, 
                   end_time, 
                   moving_window=15, 
                   pair_n=3,
                   output_dir='.',
                   double_checkinglen=False,
                   thr_on=4.5,
                   thr_of=2.7,
                   consider_combination=False):
    
    
    """
    Performs a very simple association based on detection times on multiple stations.
    It works fine when you have a small and local network of seismic stations. 

    Parameters
    ----------
       input_dir: str
           Path to a dicrectory containing detection results.
       preprocessed_dir: str
           Path to a dicrectory containing preprocessed data (hdf5 and csv files).
       start_time: str
           Start of a time period of interest in 'YYYY-MM-DD hh:mm:ss.f' format
       end_time: str
           End of a timeperiod of interest in 'YYYY-MM-DD hh:mm:ss.f' format
       moving_window: int, (default = 15)
           The length of time window used for association in second.
       pair_n: int, (default = 2)
           The minimum number of stations used for the association.  
       output_dir: str, (default = '.')
           Path to the directory to write the output file.
       double_checkinglen: bool, (default = False)
           If True, it will search for the missing events based on detected events on neirby stations using a traditional detector&picker.
       thr_on: float, (default = 4.5)
           Threshold value for traditional detector.         
       thr_of: float, (default = 2.7)
           Threshold value for traditional detector.
       consider_combination: bool, (default = False)
           If True, it will write down all possible combinations of picked arrival times for each event. 
           This will generates multiple events with a same ID, and you will need to remove those with poor solutions 
           after location. This helps to remove the false positives from associated event. 

           
    Generates
    -------
    ./output_dir/Y2000.phs
        Phase information for the associated events in hypoInverse format.
        
    ./output_dir/traceNmae_dic.json
        A dictionary where the trace name for all the detections associated to an events are listed. 
        This can be used later to access the traces for calculating the cross-correlations during the relocation process.  
               
    """         

    
    if os.path.exists("phase_dataset"):
        os.remove("phase_dataset")
    conn = sqlite3.connect("phase_dataset")
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE phase_dataset (traceID TEXT, 
                                    network TEXT,
                                    station TEXT,
                                    instrument_type TEXT,
                                    stlat NUMERIC, 
                                    stlon NUMERIC, 
                                    stelv NUMERIC,                        
                                    event_start_time DateTime, 
                                    event_end_time DateTime, 
                                    detection_prob NUMERIC, 
                                    detection_unc NUMERIC, 
                                    p_arrival_time DateTime, 
                                    p_prob NUMERIC, 
                                    p_unc NUMERIC, 
                                    p_snr NUMERIC,
                                    s_arrival_time DateTime, 
                                    s_prob NUMERIC, 
                                    s_unc NUMERIC, 
                                    s_snr NUMERIC,
                                    amp NUMERIC
                                    )''')
    
    station_list = [ev for ev in listdir(input_dir) if ev.split('/')[-1] != '.DS_Store'];
    station_list = sorted(set(station_list))

    for st in station_list:       
        print(f'reading {st} ...')
        _pick_database_maker(conn, cur, input_dir+'/'+st+'/X_prediction_results.csv')

    #  read the database as dataframe 
    conn = sqlite3.connect("phase_dataset")
    tbl = pd.read_sql_query("SELECT * FROM phase_dataset", conn); 
    #tbl = tbl[tbl.p_prob > 0.3]
    #tbl = tbl[tbl.s_prob > 0.3]

    tbl['event_start_time'] = tbl['event_start_time'].apply(lambda row : _date_convertor(row)) 
    tbl['event_end_time'] = tbl['event_end_time'].apply(lambda row : _date_convertor(row)) 
    tbl['p_arrival_time'] = tbl['p_arrival_time'].apply(lambda row : _date_convertor(row)) 
    tbl['s_arrival_time'] = tbl['s_arrival_time'].apply(lambda row : _date_convertor(row)) 

    _dbs_associator(start_time,
                    end_time,
                    moving_window,
                    tbl, 
                    pair_n,
                    output_dir,
                    station_list,
                    preprocessed_dir,
                    double_checkinglen,
                    thr_on,
                    thr_of,
                    consider_combination)
    
    os.remove("phase_dataset")






def _pick_database_maker(conn, cur, input_file):
    csv_file = open(input_file)
    csv_reader = csv.reader(csv_file, delimiter=',')
    line_count = 0
    for row in csv_reader:
        if line_count == 0:
            #  print(f'Column names are {", ".join(row)}')
            line_count += 1
        else: 
            line_count += 1
            
            traceID = row[0]
            st_time = traceID.split('_')[3].replace('T', ' ').replace('Z', '')
            mls = st_time.split('.')
            if len(mls) == 1:
                start_time = datetime.strptime(st_time, '%Y-%m-%d %H:%M:%S')
            else:
                start_time = datetime.strptime(st_time, '%Y-%m-%d %H:%M:%S.%f')
                
            network = row[1]
            station = row[2]
            instrument_type = row[3]
            stlat = float(row[4])
            stlon = float(row[5]) 
            stelv = float(row[6])                        
            
            mls = row[7].split('.')
            if len(mls) == 1:
                event_start_time = datetime.strptime(row[7], '%Y-%m-%d %H:%M:%S')
            else:
                event_start_time = datetime.strptime(row[7], '%Y-%m-%d %H:%M:%S.%f')

            mls = row[8].split('.')
            if len(mls) == 1:
                event_end_time = datetime.strptime(row[8], '%Y-%m-%d %H:%M:%S')
            else:
                event_end_time = datetime.strptime(row[8], '%Y-%m-%d %H:%M:%S.%f')
                            
            detection_prob = float(row[9]) 
            try:
                detection_unc = float(row[10]) 
            except Exception:
                detection_unc = None          

            if len(row[11]) > 10:
           #     p_arrival_time = UTCDateTime(row[11].replace(' ', 'T')+'Z')
                mls = row[11].split('.')
                if len(mls) == 1:
                    p_arrival_time = datetime.strptime(row[11], '%Y-%m-%d %H:%M:%S')
                else:
                    p_arrival_time = datetime.strptime(row[11], '%Y-%m-%d %H:%M:%S.%f')
                                    
                p_prob = float(row[12])
                try:
                    p_unc = float(row[13]) 
                except Exception:
                    p_unc = None
            else:
                p_arrival_time = None
                p_prob = None
                p_unc = None 
                
            try:
                p_snr = float(row[14]) 
            except Exception:
                p_snr = None 
                                
            if len(row[15]) > 10:
                mls = row[15].split('.')
                if len(mls) == 1:
                    s_arrival_time = datetime.strptime(row[15], '%Y-%m-%d %H:%M:%S')
                else:
                    s_arrival_time = datetime.strptime(row[15], '%Y-%m-%d %H:%M:%S.%f')                
                                
                s_prob = float(row[16])
                try:
                    s_unc = float(row[17]) 
                except Exception:
                    s_unc = None
            else:
                s_arrival_time = None
                s_prob = None
                s_unc = None   

            try:
                s_snr = float(row[18]) 
            except Exception:
                s_snr = None
                
            amp = None

            cur.execute('''INSERT INTO phase_dataset VALUES 
                        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?)''', 
                        (traceID, network, station, instrument_type, stlat, stlon, stelv,
                         event_start_time, event_end_time, detection_prob, detection_unc, 
                         p_arrival_time, p_prob, p_unc, p_snr, s_arrival_time, s_prob, s_unc, s_snr,
                         amp))
            
            conn.commit()




def _decimalDegrees2DMS(value,type):
    """
        Converts a Decimal Degree Value into
        Degrees Minute Seconds Notation.
        
        Pass value as double
        type = {Latitude or Longitude} as string
        
        returns a string as D:M:S:Direction
        created by: anothergisblog.blogspot.com 
    """
    degrees = int(value)
    submin = abs( (value - int(value) ) * 60)
    direction = ""
    if type == "Longitude":
        if degrees < 0:
            direction = "W"
        elif degrees > 0:
            direction = " "
        else:
            direction = ""
        notation = ["{:>3}".format(str(abs(degrees))), direction, "{:>5}".format(str(round(submin, 2)))] 

    elif type == "Latitude":
        if degrees < 0:
            direction = "S"
        elif degrees > 0:
            direction = " "
        else:
            direction = "" 
        notation =["{:>2}".format(str(abs(degrees))), direction, "{:>5}".format(str(round(submin, 2)))] 
        
    return notation



def _weighcalculator_prob(pr):
    weight = 4
    if pr > 0.6:
        weight = 0
    elif pr <= 0.6 and pr > 0.5:
        weight = 1
    elif pr <= 0.5 and pr > 0.2:
        weight = 2
    elif pr <= 0.2 and pr > 0.1:
        weight = 3  
    elif pr <= 0.1:
        weight = 4 
         
    return weight



def _date_convertor(r):  
          
    mls = r.split('.')
    if len(mls) == 1:
        new_t = datetime.strptime(r, '%Y-%m-%d %H:%M:%S')
    else:
        new_t = datetime.strptime(r, '%Y-%m-%d %H:%M:%S.%f')
    return new_t


def _doubleChecking(station_list, detections, preprocessed_dir, moving_window, thr_on=3.7, thr_of=0.5):

    for stt in station_list:
        sttt = stt.split('_')[0]
      #  print(sttt)
        if sttt not in detections['station'].to_list():
            new_picks = {}                    
        
            file_name = preprocessed_dir+'/'+sttt+'.hdf5'
            file_csv = preprocessed_dir+"/"+sttt+".csv"
            df = pd.read_csv(file_csv)
            df['start_time'] = pd.to_datetime(df['start_time'])  
            
            mask = (df['start_time'] > detections.iloc[0]['event_start_time']-timedelta(seconds = moving_window)) & (df['start_time'] < detections.iloc[0]['event_start_time']+timedelta(seconds = moving_window))
            df = df.loc[mask]
            dtfl = h5py.File(file_name, 'r')
            dataset = dtfl.get('data/'+df['trace_name'].to_list()[0]) 
            data = np.array(dataset)
                
            cft = recursive_sta_lta(data[:,2], int(2.5 * 100), int(10. * 100))
            on_of = trigger_onset(cft, thr_on, thr_of)
            if len(on_of) >= 1:                    
                p_pick, s_pick = ar_pick(data[:,2], data[:,1], data[:,0], 100, 1.0, 20.0, 1.0, 0.1, 4.0, 1.0, 2, 8, 0.1, 0.2)
                if (on_of[0][1]+100)/100 > p_pick > (on_of[0][0]-100)/100: 
                   # print('got one')
                    new_picks['traceID'] = df['trace_name'].to_list()[0]
                    new_picks['network'] = dataset.attrs["network_code"]
                    new_picks['station'] = sttt
                    new_picks['instrument_type'] = df['trace_name'].to_list()[0].split('_')[2]
                    new_picks['stlat'] = round(dataset.attrs["receiver_latitude"], 4)
                    new_picks['stlon'] = round(dataset.attrs["receiver_longitude"], 4)
                    new_picks['stelv'] = round(dataset.attrs["receiver_elevation_m"], 2)
                    new_picks['event_start_time'] = datetime.strptime(str(UTCDateTime(dataset.attrs['trace_start_time'].replace(' ', 'T')+'Z')+(on_of[0][0]/100)).replace('T', ' ').replace('Z', ''), '%Y-%m-%d %H:%M:%S.%f')
                    new_picks['event_end_time'] = datetime.strptime(str(UTCDateTime(dataset.attrs['trace_start_time'].replace(' ', 'T')+'Z')+(on_of[0][1]/100)).replace('T', ' ').replace('Z', ''), '%Y-%m-%d %H:%M:%S.%f')
                    new_picks['detection_prob'] = 0.3
                    new_picks['detection_unc'] = 0.6
                    new_picks['p_arrival_time'] = datetime.strptime(str(UTCDateTime(dataset.attrs['trace_start_time'].replace(' ', 'T')+'Z')+p_pick).replace('T', ' ').replace('Z', ''), '%Y-%m-%d %H:%M:%S.%f')
                    new_picks['p_prob'] = 0.3
                    new_picks['p_unc'] = 0.6
                    new_picks['p_snr'] = None
                    new_picks['s_arrival_time'] = None
                    new_picks['s_prob'] = 0.0
                    new_picks['s_unc'] = None
                    new_picks['s_snr'] = None
                    new_picks['amp'] = None
                    detections = detections.append(new_picks , ignore_index=True)      
    return detections                    
                            
                            

def _dbs_associator(start_time, end_time, moving_window, 
                    tbl, pair_n, save_dir, station_list,
                    preprocessed_dir, double_checkinglen,
                    thr_on, thr_of, consider_combination=False):  
    
    if consider_combination==True: 
        Y2000_writer = open(save_dir+'/'+'Y2000.phs', 'w')
        traceNmae_dic = dict()    
        st = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S.%f')
        et = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S.%f')
        total_t = et-st;
        evid = 0; 
        tt = st
        pbar = tqdm(total= int(np.ceil(total_t.total_seconds()/moving_window)), ncols=100) 
        while tt < et:
            
            detections = tbl[(tbl.event_start_time >= tt) & (tbl.event_start_time < tt+timedelta(seconds = moving_window))]        
            pbar.update()
            if len(detections) >= pair_n:  
                evid += 1
    
                yr = "{:>4}".format(str(detections.iloc[0]['event_start_time']).split(' ')[0].split('-')[0])
                mo = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[0].split('-')[1]) 
                dy = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[0].split('-')[2]) 
                hr = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[1].split(':')[0]) 
                mi = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[1].split(':')[1]) 
                sec = "{:>4}".format(str(detections.iloc[0]['event_start_time']).split(' ')[1].split(':')[2]) 
                st_lat_DMS = _decimalDegrees2DMS(float(detections.iloc[0]['stlat']),  "Latitude")
                st_lon_DMS = _decimalDegrees2DMS(float(detections.iloc[0]['stlon']),  "Longitude")
                depth = 5.0
                mag = 0.0
               
                if double_checkinglen and (detections) >= 2*pair_n:
                    try:
                        detections = _doubleChecking(station_list, detections, preprocessed_dir, moving_window, thr_on, thr_of)
                    except Exception:
                        pass
                      
                if len(detections)/pair_n <= 2:
                    ch = pair_n
                else:
                    ch = int(len(detections)-pair_n)
                  
                                    
                for ns in range(ch, len(detections)+1):
                    comb = 0
                    for ind in list(combinations(detections.index, ns)):
                        comb+=1
                        selected_detections = detections.loc[ind,:]
                        sorted_detections = selected_detections.sort_values('p_arrival_time')
    
                        Y2000_writer.write("%4d%2d%2d%2d%2d%4.2f%2.0f%1s%4.2f%3.0f%1s%4.2f%5.2f%3.2f\n"%
                                           (int(yr),int(mo),int(dy), int(hr),int(mi),float(sec),float(st_lat_DMS[0]), 
                                            str(st_lat_DMS[1]), float(st_lat_DMS[2]),float(st_lon_DMS[0]), str(st_lon_DMS[1]), 
                                            float(st_lon_DMS[2]),float(depth), float(mag))); 
                                
                        station_buffer=[]; row_buffer=[]; tr_names=[]; tr_names2=[]
                        for _, row in sorted_detections.iterrows():
                            
                            trace_name = row['traceID']
                            p_unc = row['p_unc']
                            p_prob = row['p_prob']
                            s_unc = row['s_unc']
                            s_prob = row['s_prob']
            
                            if p_unc:                    
                                Pweihgt = _weighcalculator_prob(p_prob*(1-p_unc))
                            else:
                                Pweihgt = _weighcalculator_prob(p_prob)
                            try:
                                Pweihgt = int(Pweihgt)
                            except Exception:
                                Pweihgt = 4
            
                            if s_unc: 
                                Sweihgt = _weighcalculator_prob(s_prob*(1-s_unc))
                            else:
                                Sweihgt = _weighcalculator_prob(s_prob)  
                            try:
                                Sweihgt = int(Sweihgt)
                            except Exception:
                                Sweihgt = 4
                                
                            station = "{:<5}".format(row['station'])
                            network = "{:<2}".format(row['network']) 
                            
                            yrp = "{:>4}".format(str(row['p_arrival_time']).split(' ')[0].split('-')[0])
                            mop = "{:>2}".format(str(row['p_arrival_time']).split(' ')[0].split('-')[1]) 
                            dyp = "{:>2}".format(str(row['p_arrival_time']).split(' ')[0].split('-')[2]) 
                            hrp = "{:>2}".format(str(row['p_arrival_time']).split(' ')[1].split(':')[0]) 
                            mip = "{:>2}".format(str(row['p_arrival_time']).split(' ')[1].split(':')[1]) 
                            sec_p = "{:>4}".format(str(row['p_arrival_time']).split(' ')[1].split(':')[2]) 
                            try:
                                sec_s = "{:>4}".format(str(row['s_arrival_time']).split(' ')[1].split(':')[2]) 
                            except Exception:
                                sec_s = None
                            
                            if row['station'] not in station_buffer:
                                tr_names.append(trace_name)
                                station_buffer.append(row['station'])                      
                                if sec_s:
                                   # LTTS.append(row['stlon'])
                                   # TTS.append(UTCDateTime(str(row['s_arrival_time']).replace(' ', 'T')+'Z')-STUTC)
                                    Y2000_writer.write("%5s%2s  HHE     %4d%2d%2d%2d%2d%5.2f       %5.2fES %1d\n"%
                                                       (station,network,int(yrp),int(mop),int(dyp),int(hrp),int(mip),
                                                        float(0.0),float(sec_s), Sweihgt))
                                if sec_p:
                                   # LTTP.append(row['stlon'])
                                   # TTP.append(UTCDateTime(str(row['p_arrival_time']).replace(' ', 'T')+'Z')-STUTC)
                                    Y2000_writer.write("%5s%2s  HHZ IP %1d%4d%2d%2d%2d%2d%5.2f       %5.2f   0\n"%
                                                       (station,network,Pweihgt,int(yrp),int(mop),int(dyp),int(hrp),
                                                        int(mip),float(sec_p),float(0.0)))                        
                            else :
                                tr_names2.append(trace_name)
                                if sec_s:
                                    row_buffer.append("%5s%2s  HHE     %4d%2d%2d%2d%2d%5.2f       %5.2fES %1d\n"%(station,network,
                                                                                                                 int(yrp),int(mop),int(dyp),
                                                                                                                 int(hrp),int(mip),0.0,
                                                                                                                 float(sec_s), Sweihgt)); 
                                if sec_p:
                                    row_buffer.append("%5s%2s  HHZ IP %1d%4d%2d%2d%2d%2d%5.2f       %5.2f   0\n"%(station,network,
                                                                                                                 Pweihgt,   
                                                                                                                 int(yrp),int(mop),int(dyp),
                                                                                                                 int(hrp),int(mip),float(sec_p),
                                                                                                                 float(0.0)));                                 
                        Y2000_writer.write("{:<62}".format(' ')+"%10d"%(evid)+'\n');
    
                traceNmae_dic[str(evid)] = tr_names
    
                if len(row_buffer) >= 2*pair_n: 
                    Y2000_writer.write("%4d%2d%2d%2d%2d%4.2f%2.0f%1s%4.2f%3.0f%1s%4.2f%5.2f%3.2f\n"%
                                       (int(yr),int(mo),int(dy),int(hr),int(mi),float(sec), 
                                        float(st_lat_DMS[0]), str(st_lat_DMS[1]), float(st_lat_DMS[2]),
                                        float(st_lon_DMS[0]), str(st_lon_DMS[1]), float(st_lon_DMS[2]),
                                        float(depth), float(mag)));   
                    for rr in row_buffer:
                        Y2000_writer.write(rr);
                 
                    Y2000_writer.write("{:<62}".format(' ')+"%10d"%(evid)+'\n');
                    traceNmae_dic[str(evid)] = tr_names2
                
    
            tt += timedelta(seconds= moving_window)
        
     #   plt.scatter(LTTP, TTP, s=10, marker='o', c='b', alpha=0.4, label='P')
     #   plt.scatter(LTTS, TTS, s=10, marker='o', c='r', alpha=0.4, label='S')
     #   plt.legend('upper right')
     #   plt.show()
        print('Number of realizations: '+str(evid)+'\n', flush=True)
            
        jj = json.dumps(traceNmae_dic)     
        f = open(save_dir+'/'+"traceNmae_dic.json","w")
        f.write(jj)
        f.close()

    else:    
        Y2000_writer = open(save_dir+'/'+'Y2000.phs', 'w')
        traceNmae_dic = dict()    
        st = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S.%f')
        et = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S.%f')
        total_t = et-st;
        evid = 200000;  evidd = 100000
        tt = st
        pbar = tqdm(total= int(np.ceil(total_t.total_seconds()/moving_window))) 
        while tt < et:
            
            detections = tbl[(tbl.event_start_time >= tt) & (tbl.event_start_time < tt+timedelta(seconds = moving_window))]        
            pbar.update()
            if len(detections) >= pair_n:   
    
                yr = "{:>4}".format(str(detections.iloc[0]['event_start_time']).split(' ')[0].split('-')[0])
                mo = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[0].split('-')[1]) 
                dy = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[0].split('-')[2]) 
                hr = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[1].split(':')[0]) 
                mi = "{:>2}".format(str(detections.iloc[0]['event_start_time']).split(' ')[1].split(':')[1]) 
                sec = "{:>4}".format(str(detections.iloc[0]['event_start_time']).split(' ')[1].split(':')[2]) 
                st_lat_DMS = _decimalDegrees2DMS(float(detections.iloc[0]['stlat']),  "Latitude")
                st_lon_DMS = _decimalDegrees2DMS(float(detections.iloc[0]['stlon']),  "Longitude")
                depth = 5.0
                mag = 0.0
    
                Y2000_writer.write("%4d%2d%2d%2d%2d%4.2f%2.0f%1s%4.2f%3.0f%1s%4.2f%5.2f%3.2f\n"%(int(yr),int(mo),int(dy),
                                                                                             int(hr),int(mi),float(sec), 
                                                                                             float(st_lat_DMS[0]), str(st_lat_DMS[1]), float(st_lat_DMS[2]),
                                                                                             float(st_lon_DMS[0]), str(st_lon_DMS[1]), float(st_lon_DMS[2]),
                                                                                             float(depth), float(mag)));            
                station_buffer = []
                row_buffer = []
                sorted_detections = detections.sort_values('p_arrival_time')
                tr_names = []
                tr_names2 = []
                for _, row in sorted_detections.iterrows():
                    trace_name = row['traceID']
                    p_unc = row['p_unc']
                    p_prob = row['p_prob']
                    s_unc = row['s_unc']
                    s_prob = row['s_prob']
    
                    if p_unc:                    
                        Pweihgt = _weighcalculator_prob(p_prob*(1-p_unc))
                    else:
                        Pweihgt =_weighcalculator_prob(p_prob)
                    try:
                        Pweihgt = int(Pweihgt)
                    except Exception:
                        Pweihgt = 4
    
                    if s_unc: 
                        Sweihgt = _weighcalculator_prob(s_prob*(1-s_unc))
                    else:
                        Sweihgt = _weighcalculator_prob(s_prob)  
                    try:
                        Sweihgt = int(Sweihgt)
                    except Exception:
                        Sweihgt = 4
                        
                    station = "{:<5}".format(row['station'])
                    network = "{:<2}".format(row['network']) 
                    
                    yrp = "{:>4}".format(str(row['p_arrival_time']).split(' ')[0].split('-')[0])
                    mop = "{:>2}".format(str(row['p_arrival_time']).split(' ')[0].split('-')[1]) 
                    dyp = "{:>2}".format(str(row['p_arrival_time']).split(' ')[0].split('-')[2]) 
                    hrp = "{:>2}".format(str(row['p_arrival_time']).split(' ')[1].split(':')[0]) 
                    mip = "{:>2}".format(str(row['p_arrival_time']).split(' ')[1].split(':')[1]) 
                    sec_p = "{:>4}".format(str(row['p_arrival_time']).split(' ')[1].split(':')[2]) 
                    sec_s = "{:>4}".format(str(row['s_arrival_time']).split(' ')[1].split(':')[2]) 
    
                    if row['station'] not in station_buffer:
                        tr_names.append(trace_name)
                        station_buffer.append(row['station'])  
                        if sec_s:
                            Y2000_writer.write("%5s%2s  HHE     %4d%2d%2d%2d%2d%5.2f       %5.2fES %1d\n"%(station,network,
                                                                                                         int(yrp),int(mop),int(dyp),
                                                                                                         int(hrp),int(mip),float(0.0),
                                                                                                         float(sec_s), Sweihgt))
                        if sec_p:
                            Y2000_writer.write("%5s%2s  HHZ IP %1d%4d%2d%2d%2d%2d%5.2f       %5.2f   0\n"%(station,network,
                                                                                                         Pweihgt,   
                                                                                                         int(yrp),int(mop),int(dyp),
                                                                                                         int(hrp),int(mip),float(sec_p),
                                                                                                         float(0.0)))                        
                    else :
                        tr_names2.append(trace_name)
                        if sec_s:
                            row_buffer.append("%5s%2s  HHE     %4d%2d%2d%2d%2d%5.2f       %5.2fES %1d\n"%(station,network,
                                                                                                         int(yrp),int(mop),int(dyp),
                                                                                                         int(hrp),int(mip),0.0,
                                                                                                         float(sec_s), Sweihgt)); 
                        if sec_p:
                            row_buffer.append("%5s%2s  HHZ IP %1d%4d%2d%2d%2d%2d%5.2f       %5.2f   0\n"%(station,network,
                                                                                                         Pweihgt,   
                                                                                                         int(yrp),int(mop),int(dyp),
                                                                                                         int(hrp),int(mip),float(sec_p),
                                                                                                         float(0.0))); 
    
                evid += 1
                Y2000_writer.write("{:<62}".format(' ')+"%10d"%(evid)+'\n');
                traceNmae_dic[str(evid)] = tr_names
    
                if len(row_buffer) >= 2*pair_n: 
                    Y2000_writer.write("%4d%2d%2d%2d%2d%4.2f%2.0f%1s%4.2f%3.0f%1s%4.2f%5.2f%3.2f\n"%
                                       (int(yr),int(mo),int(dy),int(hr),int(mi),float(sec), 
                                        float(st_lat_DMS[0]), str(st_lat_DMS[1]), float(st_lat_DMS[2]),
                                        float(st_lon_DMS[0]), str(st_lon_DMS[1]), float(st_lon_DMS[2]),
                                        float(depth), float(mag)));   
                    for rr in row_buffer:
                        Y2000_writer.write(rr);
                 
                    evid += 1
                    Y2000_writer.write("{:<62}".format(' ')+"%10d"%(evid)+'\n');
                    traceNmae_dic[str(evid)] = tr_names2
                    
                elif len(row_buffer) < pair_n and len(row_buffer) != 0:
                    evidd += 1
                    traceNmae_dic[str(evidd)] = tr_names2
                    
            elif len(detections) < pair_n and len(detections) != 0:
                tr_names = []
                for _, row in detections.iterrows():
                    trace_name = row['traceID']
                    tr_names.append(trace_name)
                evidd += 1
                traceNmae_dic[str(evidd)] = tr_names                
    
            tt += timedelta(seconds= moving_window)
        print('Number of multi-station detections: '+str(evid-200000)+'\n', flush=True)
        print('Number of single-station detections: '+str(evidd-100000)+'\n', flush=True)
            
        jj = json.dumps(traceNmae_dic)     
        f = open(save_dir+'/'+"traceNmae_dic.json","w")
        f.write(jj)
        f.close()
        
