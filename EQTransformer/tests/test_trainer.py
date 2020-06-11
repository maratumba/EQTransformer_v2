#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Jan 25 22:34:05 2020

@author: mostafamousavi
"""

from EQTransformer.core.trainer import trainer
import pytest
import glob
import os

def test_generator():
    trainer(input_hdf5='test_data/waveforms.hdf5',
            input_csv='test_data/metadata.csv',
            output_name='test_trainer',                
            cnn_blocks=2,
            lstm_blocks=1,
            drop_rate=0.2,
            label_type='gaussian',
            add_event_r=0.6,
            shift_event_r=0.9,
            add_noise_r=0.5, 
            mode='generator',
            batch_size=200,
            epochs=1, 
            patience=2,
            gpuid=None,
            gpu_limit=None)
    
    dir_list = [ev for ev in os.listdir('.') if ev.split('_')[-1] == 'outputs']  
    if 'test_trainer_outputs'  in dir_list:
        successful = True
    else:
        successful = False        
    assert successful == True
    
    
def test_report():
    report = glob.glob("test_trainer_outputs/X_report.txt")
    assert len(report) == 1
    
def test_tests():
    tests = glob.glob("test_trainer_outputs/test.npy")
    assert len(tests) == 1

def test_hist():
    hist = glob.glob("test_trainer_outputs/history.npy")
    assert len(hist) == 1

def test_models():
    models = glob.glob("test_trainer_outputs/*.h5")
    assert len(models) == 2
    
def test_plots():
    learning_cr = glob.glob("test_trainer_outputs/*.png")
    assert len(learning_cr) == 2