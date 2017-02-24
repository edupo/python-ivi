"""

Python Interchangeable Virtual Instrument Library

Copyright (c) 2016 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

from .tektronixDPO5000 import *

MeasurementFunctionMapping = {
        'rise_time': 'rise',
        'fall_time': 'fall',
        'frequency': 'frequency',
        'period': 'period',
        'voltage_rms': 'rms',
        'voltage_peak_to_peak': 'pk2pk',
        'voltage_max': 'maximum',
        'voltage_min': 'minimum',
        'voltage_high': 'high',
        'voltage_low': 'low',
        'voltage_average': 'mean',
        'width_negative': 'nwidth',
        'width_positive': 'pwidth',
        'duty_cycle_negative': 'nduty',
        'duty_cycle_positive': 'pduty',
        'amplitude': 'amplitude',
        'voltage_cycle_rms': 'crms',
        'voltage_cycle_average': 'cmean',
        'overshoot': 'tovershoot',

        'area': 'area',
        'burst': 'burst',
        'cycle_area': 'carea',
        'overshoot_negative': 'novershoot',
        'overshoot_positive': 'povershoot',
        'edgecount_negative': 'nedgecount',
        'edgecount_positive': 'pedgecount',
        'pulsecount_negative': 'npulsecount',
        'pulsecount_positive': 'ppulsecount',

        'histogram_hits': 'hits',
        'histogram_peak_hits': 'peakhits',
        'histogram_median': 'median',
        'histogram_sigma1': 'sigma1',
        'histogram_sigma2': 'sigma2',
        'histogram_sigma3': 'sigma3',
        'histogram_stdev': 'stdev',
        'histogram_waveforms': 'waveforms',

        'phase': 'phase',
        'delay': 'delay'}

class tektronixMSO5000(tektronixDPO5000):
    "Tektronix MSO4000 series IVI oscilloscope driver"

    def __init__(self, *args, **kwargs):
        self.__dict__.setdefault('_instrument_id', 'MSO5000')

        super(tektronixMSO5000, self).__init__(*args, **kwargs)

        self._analog_channel_count = 4
        self._digital_channel_count = 16
        self._bandwidth = 1e9

        self._identity_description = "Tektronix MSO5000 series IVI oscilloscope driver"
        self._identity_supported_instrument_models = ['MSO5034', 'MSO5054', 'MSO5104',
                'MSO5204', 'MSO5034B', 'MSO5054B', 'MSO5104B', 'MSO5204B']

        self._init_channels()
