#!/usr/bin/python
#
# Copyright 2019 Steve White
#
# Permission is hereby granted, free of charge, to any person obtaining 
# a copy of this software and associated documentation files (the 'Software'), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included 
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL 
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.
#

from utils import bits_to_string, bits_to_bytes, bytes_to_num, bits_invert, num_to_bits, bits_to_num
import wires
from math import log
import re

tiles = {}

class Tile:
    name = None
    type = None
    columns = 0
    rows = 0
    slices = 0
    values = {}
    formatters = {}
    annotations = {}
    encoders = {}
    key_transformers = {}
    defaults = {}
    bitmapTable = None
    
    def __init__(self, name, type, columns, rows, slices, values, formatters={}, annotations={}, encoders={}, key_transformers={}, defaults={}):
        self.name = name
        self.type = type
        self.columns = columns
        self.rows = rows
        self.slices = slices
        self.values = values
        self.formatters = formatters
        self.formatters['__NAME'] = lambda key,val: val
        self.annotations = annotations
        self.encoders = encoders
        self.key_transformers = key_transformers
        self.defaults = defaults
    
    def buildBitmapTable(self):
        bitmapTable = [];
        for bit in range(0, self.columns * self.rows):
            matched = False
            for name in self.values:
                if bit in self.values[name]:
                    bitmapTable.append((name, self.values[name].index(bit)))
                    matched = True
                    break
            if matched == False:
                bitmapTable.append(None)
        self.bitmapTable = bitmapTable
    
    def bit_owner(self, bit):
        if self.bitmapTable is None:
            self.buildBitmapTable()
        
        return self.bitmapTable[bit]
    
    def bit_format(self, name, bits):
        if name in self.formatters:
            return self.formatters[name](name,bits)
        for pattern in self.formatters:
            if re.match(pattern, name):
                return self.formatters[pattern](name,bits)
        return bits_to_string(bits, 0, True)
    
    def format(self, name, bits, x, y, routing=None):
        result = self.bit_format(name, bits)
        if name in self.annotations:
            result += "\t; "+self.annotations[name]
        else:
            for pattern in self.annotations:
                if re.match(pattern, name):
                    result += "\t; "+self.annotations[pattern]
                    break
            
        if name.lower().find("mux") != -1:
            value = mux_decode(bits)
            if value != -1:
                wire = wires.input_for_tile_config(self.type, x, y, name, value)
                if wire is not None:
                    source = "%s(%s,%s):%s:%s %s %s" % (wire['tile'], wire['x'], wire['y'], wire['config'], wire['index'], wire['wire'], wire['timing'])
                    result += "\t; <= " + source
        if routing != None:
            net = routing.net_for_tile_config(x, y, name)
            if net is not None:
                result += '\t; ' + net
        return result
        
    def encode(self, key, value, bits, use_encoder=True):
        for pattern in self.key_transformers:
            if re.match(pattern, key):
                key = self.key_transformers[pattern](key)
                if type(key) is not str:
                    return key
                break
        
        if key not in self.values:
            print("Can't find key:%s in %s values" % (key, self.type))
            return None    
        
        if use_encoder:
            for pattern in self.encoders:
                if re.match(pattern, key):
                    value = self.encoders[pattern](key,value)
                    break
                
        indices = self.values[key]
        assert len(indices) == len(value)

        val_index = 0
        for bit_index in indices:
            bits[bit_index] = value[val_index]
            val_index += 1
        
        return True
        
    def decode(self, bits):
        values = { '__NAME': self.name }
        for idx in range(0, len(bits)):
            owner = self.bit_owner(idx)
            if owner != None:
                name = owner[0]
                position = owner[1]
            
                if name not in values:
                    values[name] = [None] * len(self.values[name])
            
                values[name][position] = bits[idx]
        return values
        
    def empty_bits(self):
        bits = [1] * (self.columns * self.rows)
        for key in self.values:
            for bit_idx in self.values[key]:
                bits[bit_idx] = 0
            for pattern in self.defaults:
                if re.match(pattern, key):
                    values = self.defaults[pattern]
                    src_idx = 0
                    for dst_idx in self.values[key]:
                        bits[dst_idx] = values[src_idx]
                        src_idx += 1
                    break
        return bits

def mux_encode(val, bit_len, val_len):
    if type(val) != int:
        val = bits_to_num(val)
    if val_len > 0:
        length = bit_len * val_len
        assert(val <= length)
        if val == -1:
            result = [0] * (bit_len + val_len)
        else:
            bottom = 1 << (val_len - 1 - int(val / bit_len))
            top = 1 << (bit_len - 1 - (val % bit_len))
            result = num_to_bits((top << val_len) | bottom, bit_len + val_len)
        assert val == mux_decode(result, bit_len)
    else:
        length = bit_len
        assert(val <= length)
        result = num_to_bits(1 << (bit_len-1-val), bit_len)
    return result

def mux_decode(bits, length=None):
    if length:
        X = len(bits) - length
    else:
        X = 3
        length = len(bits) - X
    
    strval = bits_to_string(bits)
    val = int(strval, 2)
    if val == 0:
        return -1
    
    top = val >> X
    bottom = val & ((1<<X)-1)
    
    if top == 0 or bottom == 0:
        return -1

    return int(((length-1) - log(top, 2)) + (length * (X - 1 - log(bottom, 2))))
    
def mux_format(bits, length, type):
    index = mux_decode(bits, length)
    return '%s\'b%s_%s\t; %s:%s' % (len(bits), bits_to_string(bits[0:length]), bits_to_string(bits[length:]), type, int(index)) 

def lut_slice_from_key(key):
    if key.startswith("alta_slice") and key.endswith("_LUT"):
        return int(key[10:-4])
    return None

def lut_encode(key, inbits):
    outbits = bits_invert(inbits)
    return outbits[::-1]

def lut_decode(key, inbits):
    outbits = bits_invert(inbits)
    return outbits[::-1]

def slice_omux_format(bits):
    if bits[0] == 0:
        name = 'LutOut'
    else:
        name = 'Q'
    return '1\'b%s\t; %s' % (bits[0], name)

def InstallTile(tile):
    global tiles
    tiles[tile.name] = tile

def TileNamed(name):
    global tiles
    return tiles[name]

InstallTile(Tile('AG1200_IOTILE_BOOT_PLL', 'UFMTILE', columns=34, rows=20, slices=0, values={
	# Each BBMUXE0 contains 1 entry of 9 bits each
	'BBMUXE00': [ 498, 532, 497, 531, 496, 530, 495, 529, 526 ],
	'BBMUXE01': [ 506, 540, 505, 539, 504, 538, 503, 537, 534 ],
	'BBMUXE02': [ 566, 600, 565, 599, 564, 598, 563, 597, 594 ],
	'BBMUXE03': [ 574, 608, 573, 607, 572, 606, 571, 605, 602 ],
	'BBMUXE04': [ 634, 668, 633, 667, 632, 666, 631, 665, 662 ],
	'BBMUXE05': [ 642, 676, 641, 675, 640, 674, 639, 673, 670 ],

	# Each BBMUXN0 contains 1 entry of 9 bits each
	'BBMUXN00': [ 90, 124, 89, 123, 88, 122, 87, 121, 118 ],
	'BBMUXN01': [ 98, 132, 97, 131, 96, 130, 95, 129, 126 ],
	'BBMUXN02': [ 158, 192, 157, 191, 156, 190, 155, 189, 186 ],
	'BBMUXN03': [ 166, 200, 165, 199, 164, 198, 163, 197, 194 ],

	'GdrvMUX00': [ 268, 234, 267, 233, 266, 265, 264, 263, 232, 231, 230, 229 ],

	'SeamMUX00':[287,288,289,290,291,292,293,294],
	'SeamMUX01':[321,322,323,324,325,326,327,328],
	'SeamMUX02':[355,356,357,358,359,360,361,362],
	'SeamMUX03':[389,390,391,392,393,394,395,396],
	'SeamMUX04':[423,424,425,426,427,428,429,430],
	'SeamMUX05':[431,432,433,434,435,436,437,438],
	'SeamMUX06':[397,398,399,400,401,402,403,404],
	'SeamMUX07':[363,364,365,366,367,368,369,370],
	'SeamMUX08':[329,330,331,332,333,334,335,336],
	'SeamMUX09':[295,296,297,298,299,300,301,302],
}, encoders={
	'BBMUXN[0-9][0-9]': lambda key,val: mux_encode(val, 7, 2),
    'BBMUXE[0-9][0-9]': lambda key,val: mux_encode(val, 7, 2),
}))

InstallTile(Tile('AG1200_IOTILE_N4_G1', 'IOTILE', columns=34, rows=20, slices=4, values={
	# Tile is identical to AG1200_IOTILE_N4, with the addition of CFG_GclkDMUX00

	# Each CtrlMUX contains 2 entries of 6 bits each
	'CtrlMUX00': [ 274, 308, 273, 307, 272, 306, 342, 376, 341, 375, 340, 374 ],
	'CtrlMUX01': [ 280, 314, 279, 313, 278, 312, 348, 382, 347, 381, 346, 380 ],
	'CtrlMUX02': [ 275, 309, 276, 310, 277, 311, 343, 377, 344, 378, 345, 379 ],
	'CtrlMUX03': [ 281, 315, 282, 316, 283, 317, 349, 383, 350, 384, 351, 385 ],

	'GclkDMUX00': [ 235, 474, 473, 236 ],

	'InputMUX00':[33],
	'InputMUX01':[135],
	'InputMUX02':[169],
	'InputMUX03':[237],
	'InputMUX04':[679],
	'InputMUX05':[577],
	'InputMUX06':[543],
	'InputMUX07':[475],

	'IOMUX00':[18,52,17,51,16,50,49],
	'IOMUX01':[86,120,85,119,84,118,117],
	'IOMUX02':[630,664,629,663,628,662,661],
	'IOMUX03':[562,596,561,595,560,594,593],
	'IOMUX04':[154,188,153,187,152,186,185],
	'IOMUX05':[222,256,221,255,220,254,253],
	'IOMUX06':[494,528,493,527,492,526,525],
	'IOMUX07':[426,460,425,459,424,458,457],
	'IOMUX08':[155,189,156,190,157,191,192],
	'IOMUX09':[223,257,224,258,225,259,260],
	'IOMUX10':[495,529,496,530,497,531,532],
	'IOMUX11':[427,461,428,462,429,463,464],
	'IOMUX12':[19,53,20,54,21,55,56],
	'IOMUX13':[87,121,88,122,89,123,124],
	'IOMUX14':[631,665,632,666,633,667,668],
	'IOMUX15':[563,597,564,598,565,599,600],
	'IOMUX16':[26,60,25,59,24,58,57],
	'IOMUX17':[94,128,93,127,92,126,125],
	'IOMUX18':[638,672,637,671,636,670,669],
	'IOMUX19':[570,604,569,603,568,602,601],
	'IOMUX20':[162,196,161,195,160,194,193],
	'IOMUX21':[230,264,229,263,228,262,261],
	'IOMUX22':[502,536,501,535,500,534,533],
	'IOMUX23':[434,468,433,467,432,466,465],

	# Each of these contains 4 entries of 1 bit each
	'IN_ASYNC_MODE': [ 28, 31, 674, 677 ],
	'IN_POWERUP': [ 61, 66, 639, 644 ],
	'IN_SYNC_MODE': [ 27, 32, 673, 678 ],
	'OE_ASYNC_MODE': [ 164, 167, 538, 541 ],
	'OE_POWERUP': [ 197, 202, 503, 508 ],
	'OE_REG_MODE': [ 130, 133, 572, 575 ],
	'OE_SYNC_MODE': [ 163, 168, 537, 542 ],
	'OUT_ASYNC_MODE': [ 96, 99, 606, 609 ],
	'OUT_POWERUP': [ 129, 134, 571, 576 ],
	'OUT_REG_MODE': [ 198, 201, 504, 507 ],
	'OUT_SYNC_MODE': [ 95, 100, 605, 610 ],

	'RMUX00':[2,36,1,0,35,34],
	'RMUX01':[70,104,69,68,103,102],
	'RMUX02':[138,172,137,136,171,170],
	'RMUX03':[206,240,205,204,239,238],
	'RMUX04':[614,648,613,612,647,646],
	'RMUX05':[546,580,545,544,579,578],
	'RMUX06':[478,512,477,476,511,510],
	'RMUX07':[410,444,409,408,443,442],
	'RMUX08':[3,37,4,5,38,39],
	'RMUX09':[71,105,72,73,106,107],
	'RMUX10':[139,173,140,141,174,175],
	'RMUX11':[207,241,208,209,242,243],
	'RMUX12':[615,649,616,617,650,651],
	'RMUX13':[547,581,548,549,582,583],
	'RMUX14':[479,513,480,481,514,515],
	'RMUX15':[411,445,412,413,446,447],
	'RMUX16':[8,42,7,6,41,40],
	'RMUX17':[76,110,75,74,109,108],
	'RMUX18':[144,178,143,142,177,176],
	'RMUX19':[212,246,211,210,245,244],
	'RMUX20':[620,654,619,618,653,652],
	'RMUX21':[552,586,551,550,585,584],
	'RMUX22':[484,518,483,482,517,516],
	'RMUX23':[416,450,415,414,449,448],
	'RMUX24':[9,43,10,11,44,45],
	'RMUX25':[77,111,78,79,112,113],
	'RMUX26':[145,179,146,147,180,181],
	'RMUX27':[213,247,214,215,248,249],
	'RMUX28':[621,655,622,623,656,657],
	'RMUX29':[553,587,554,555,588,589],
	'RMUX30':[485,519,486,487,520,521],
	'RMUX31':[417,451,418,419,452,453],

	'SeamMUX00':[287,288,289,290,291,292,293,294],
	'SeamMUX01':[389,390,391,392,393,394,395,396],
	'SeamMUX02':[321,322,323,324,325,326,327,328],
	'SeamMUX03':[355,356,357,358,359,360,361,362],
	'SeamMUX04':[295,296,297,298,299,300,266,265],
	'SeamMUX05':[397,398,399,400,401,402,436,435],
	'SeamMUX06':[329,330,331,332,333,334,232,231],
	'SeamMUX07':[363,364,365,366,367,368,470,469],

	'TileClkMUX00':[303,302,269],
	'TileClkMUX01':[405,404,439],
	'TileClkMUX02':[337,336,268],
	'TileClkMUX03':[371,370,438],
	'TileClkMUX04':[304,305,270],
	'TileClkMUX05':[406,407,440],
	'TileClkMUX06':[338,339,271],
	'TileClkMUX07':[372,373,441],
}, formatters={
	'RMUX[0-9][0-9]': lambda key,val: mux_format(val, 3, 'I'),
	'IOMUX[0-9][0-9]': lambda key,val: mux_format(val, 4, 'I'),
	'TileClkMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 3, True),
	'CtrlMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 6, True),
	'GclkDMUX00': lambda key,val: bits_to_string(bits_invert(val), 6, True),
}, key_transformers={
    'alta_rio[0-9][0-9].[A-Z]*_USED': lambda x: None,
}, encoders={
	'CtrlMUX[0-9][0-9]': lambda key,val: mux_encode(val, 8, 4),
	'RMUX[0-9][0-9]': lambda key,val: mux_encode(val, 3, 3),
	'IOMUX[0-9][0-9]': lambda key,val: mux_encode(val, 4, 3),
	'TileClkMUX[0-9][0-9]': lambda key,val: mux_encode(val, 2, 1),
    'GclkDMUX00': lambda key,val: bits_invert(([0] * (4 - len(val))) + val),
}, defaults={
	'TileClkMUX[0-9][0-9]': [0,0,1],
	'IOMUX[0-9][0-9]': [0, 0, 0, 0, 0, 0, 1],
}))

InstallTile(Tile('AG1200_IOTILE_N4', 'IOTILE', columns=34, rows=20, slices=4, values={
	# Each CtrlMUX contains 2 entries of 6 bits each
	'CtrlMUX00': [ 274, 308, 273, 307, 272, 306, 342, 376, 341, 375, 340, 374 ],
	'CtrlMUX01': [ 280, 314, 279, 313, 278, 312, 348, 382, 347, 381, 346, 380 ],
	'CtrlMUX02': [ 275, 309, 276, 310, 277, 311, 343, 377, 344, 378, 345, 379 ],
	'CtrlMUX03': [ 281, 315, 282, 316, 283, 317, 349, 383, 350, 384, 351, 385 ],

	'InputMUX00':[33],
	'InputMUX01':[135],
	'InputMUX02':[169],
	'InputMUX03':[237],
	'InputMUX04':[679],
	'InputMUX05':[577],
	'InputMUX06':[543],
	'InputMUX07':[475],

	'IOMUX00':[18,52,17,51,16,50,49],
	'IOMUX01':[86,120,85,119,84,118,117],
	'IOMUX02':[630,664,629,663,628,662,661],
	'IOMUX03':[562,596,561,595,560,594,593],
	'IOMUX04':[154,188,153,187,152,186,185],
	'IOMUX05':[222,256,221,255,220,254,253],
	'IOMUX06':[494,528,493,527,492,526,525],
	'IOMUX07':[426,460,425,459,424,458,457],
	'IOMUX08':[155,189,156,190,157,191,192],
	'IOMUX09':[223,257,224,258,225,259,260],
	'IOMUX10':[495,529,496,530,497,531,532],
	'IOMUX11':[427,461,428,462,429,463,464],
	'IOMUX12':[19,53,20,54,21,55,56],
	'IOMUX13':[87,121,88,122,89,123,124],
	'IOMUX14':[631,665,632,666,633,667,668],
	'IOMUX15':[563,597,564,598,565,599,600],
	'IOMUX16':[26,60,25,59,24,58,57],
	'IOMUX17':[94,128,93,127,92,126,125],
	'IOMUX18':[638,672,637,671,636,670,669],
	'IOMUX19':[570,604,569,603,568,602,601],
	'IOMUX20':[162,196,161,195,160,194,193],
	'IOMUX21':[230,264,229,263,228,262,261],
	'IOMUX22':[502,536,501,535,500,534,533],
	'IOMUX23':[434,468,433,467,432,466,465],

	# Each of these contains 4 entries of 1 bit each
	'IN_ASYNC_MODE': [ 28, 31, 674, 677 ],
	'IN_POWERUP': [ 61, 66, 639, 644 ],
	'IN_SYNC_MODE': [ 27, 32, 673, 678 ],
	'OE_ASYNC_MODE': [ 164, 167, 538, 541 ],
	'OE_POWERUP': [ 197, 202, 503, 508 ],
	'OE_REG_MODE': [ 130, 133, 572, 575 ],
	'OE_SYNC_MODE': [ 163, 168, 537, 542 ],
	'OUT_ASYNC_MODE': [ 96, 99, 606, 609 ],
	'OUT_POWERUP': [ 129, 134, 571, 576 ],
	'OUT_REG_MODE': [ 198, 201, 504, 507 ],
	'OUT_SYNC_MODE': [ 95, 100, 605, 610 ],

	'RMUX00':[2,36,1,0,35,34],
	'RMUX01':[70,104,69,68,103,102],
	'RMUX02':[138,172,137,136,171,170],
	'RMUX03':[206,240,205,204,239,238],
	'RMUX04':[614,648,613,612,647,646],
	'RMUX05':[546,580,545,544,579,578],
	'RMUX06':[478,512,477,476,511,510],
	'RMUX07':[410,444,409,408,443,442],
	'RMUX08':[3,37,4,5,38,39],
	'RMUX09':[71,105,72,73,106,107],
	'RMUX10':[139,173,140,141,174,175],
	'RMUX11':[207,241,208,209,242,243],
	'RMUX12':[615,649,616,617,650,651],
	'RMUX13':[547,581,548,549,582,583],
	'RMUX14':[479,513,480,481,514,515],
	'RMUX15':[411,445,412,413,446,447],
	'RMUX16':[8,42,7,6,41,40],
	'RMUX17':[76,110,75,74,109,108],
	'RMUX18':[144,178,143,142,177,176],
	'RMUX19':[212,246,211,210,245,244],
	'RMUX20':[620,654,619,618,653,652],
	'RMUX21':[552,586,551,550,585,584],
	'RMUX22':[484,518,483,482,517,516],
	'RMUX23':[416,450,415,414,449,448],
	'RMUX24':[9,43,10,11,44,45],
	'RMUX25':[77,111,78,79,112,113],
	'RMUX26':[145,179,146,147,180,181],
	'RMUX27':[213,247,214,215,248,249],
	'RMUX28':[621,655,622,623,656,657],
	'RMUX29':[553,587,554,555,588,589],
	'RMUX30':[485,519,486,487,520,521],
	'RMUX31':[417,451,418,419,452,453],

	'SeamMUX00':[287,288,289,290,291,292,293,294],
	'SeamMUX01':[389,390,391,392,393,394,395,396],
	'SeamMUX02':[321,322,323,324,325,326,327,328],
	'SeamMUX03':[355,356,357,358,359,360,361,362],
	'SeamMUX04':[295,296,297,298,299,300,266,265],
	'SeamMUX05':[397,398,399,400,401,402,436,435],
	'SeamMUX06':[329,330,331,332,333,334,232,231],
	'SeamMUX07':[363,364,365,366,367,368,470,469],

	'TileClkMUX00':[303,302,269],
	'TileClkMUX01':[405,404,439],
	'TileClkMUX02':[337,336,268],
	'TileClkMUX03':[371,370,438],
	'TileClkMUX04':[304,305,270],
	'TileClkMUX05':[406,407,440],
	'TileClkMUX06':[338,339,271],
	'TileClkMUX07':[372,373,441],
}, formatters={
	'RMUX[0-9][0-9]': lambda key,val: mux_format(val, 3, 'I'),
	'IOMUX[0-9][0-9]': lambda key,val: mux_format(val, 4, 'I'),
	'TileClkMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 3, True),
	'CtrlMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 6, True)
}, key_transformers={
    'alta_rio[0-9][0-9].[A-Z]*_USED': lambda x: None,
}, encoders={
	'CtrlMUX[0-9][0-9]': lambda key,val: mux_encode(val, 8, 4),
	'RMUX[0-9][0-9]': lambda key,val: mux_encode(val, 3, 3),
	'IOMUX[0-9][0-9]': lambda key,val: mux_encode(val, 4, 3),
	'TileClkMUX[0-9][0-9]': lambda key,val: mux_encode(val, 2, 1),
}, defaults={
	'TileClkMUX[0-9][0-9]': [0,0,1],
	'IOMUX[0-9][0-9]': [0, 0, 0, 0, 0, 0, 1],
}))

InstallTile(Tile('AG1200_IOTILE_S4_G1', 'IOTILE', columns=34, rows=20, slices=4, values={
	# Tile is identical to AG1200_TILE_S4, with the addition of CFG_GclkDMUX00
	# Each CtrlMUX contains 2 entries of 6 bits each
	'CtrlMUX00': [ 376, 342, 375, 341, 374, 340, 308, 274, 307, 273, 306, 272 ],
	'CtrlMUX01': [ 382, 348, 381, 347, 380, 346, 314, 280, 313, 279, 312, 278 ],
	'CtrlMUX02': [ 377, 343, 378, 344, 379, 345, 309, 275, 310, 276, 311, 277 ],
	'CtrlMUX03': [ 383, 349, 384, 350, 385, 351, 315, 281, 316, 282, 317, 283 ],

	'GclkDMUX00': [ 473, 236, 235, 474 ],

	'InputMUX00':[679],
	'InputMUX01':[577],
	'InputMUX02':[543],
	'InputMUX03':[475],
	'InputMUX04':[33],
	'InputMUX05':[135],
	'InputMUX06':[169],
	'InputMUX07':[237],

	'IOMUX00':[664,630,663,629,662,628,627],
	'IOMUX01':[596,562,595,561,594,560,559],
	'IOMUX02':[52,18,51,17,50,16,15],
	'IOMUX03':[120,86,119,85,118,84,83],
	'IOMUX04':[528,494,527,493,526,492,491],
	'IOMUX05':[460,426,459,425,458,424,423],
	'IOMUX06':[188,154,187,153,186,152,151],
	'IOMUX07':[256,222,255,221,254,220,219],
	'IOMUX08':[529,495,530,496,531,497,498],
	'IOMUX09':[461,427,462,428,463,429,430],
	'IOMUX10':[189,155,190,156,191,157,158],
	'IOMUX11':[257,223,258,224,259,225,226],
	'IOMUX12':[665,631,666,632,667,633,634],
	'IOMUX13':[597,563,598,564,599,565,566],
	'IOMUX14':[53,19,54,20,55,21,22],
	'IOMUX15':[121,87,122,88,123,89,90],
	'IOMUX16':[672,638,671,637,670,636,635],
	'IOMUX17':[604,570,603,569,602,568,567],
	'IOMUX18':[60,26,59,25,58,24,23],
	'IOMUX19':[128,94,127,93,126,92,91],
	'IOMUX20':[536,502,535,501,534,500,499],
	'IOMUX21':[468,434,467,433,466,432,431],
	'IOMUX22':[196,162,195,161,194,160,159],
	'IOMUX23':[264,230,263,229,262,228,227],

	# Each of these contains 4 entries of 1 bit each
	'IN_ASYNC_MODE': [ 674, 677, 28, 31 ],
	'IN_POWERUP': [ 639, 644, 61, 66 ],
	'IN_SYNC_MODE': [ 673, 678, 27, 32 ],
	'OE_ASYNC_MODE': [ 538, 541, 164, 167 ],
	'OE_POWERUP': [ 503, 508, 197, 202 ],
	'OE_REG_MODE': [ 572, 575, 130, 133 ],
	'OE_SYNC_MODE': [ 537, 542, 163, 168 ],
	'OUT_ASYNC_MODE': [ 606, 609, 96, 99 ],
	'OUT_POWERUP': [ 571, 576, 129, 134 ],
	'OUT_REG_MODE': [ 504, 507, 198, 201 ],
	'OUT_SYNC_MODE': [ 605, 610, 95, 100 ],

	'RMUX00':[648,614,647,646,613,612],
	'RMUX01':[580,546,579,578,545,544],
	'RMUX02':[512,478,511,510,477,476],
	'RMUX03':[444,410,443,442,409,408],
	'RMUX04':[36,2,35,34,1,0],
	'RMUX05':[104,70,103,102,69,68],
	'RMUX06':[172,138,171,170,137,136],
	'RMUX07':[240,206,239,238,205,204],
	'RMUX08':[649,615,650,651,616,617],
	'RMUX09':[581,547,582,583,548,549],
	'RMUX10':[513,479,514,515,480,481],
	'RMUX11':[445,411,446,447,412,413],
	'RMUX12':[37,3,38,39,4,5],
	'RMUX13':[105,71,106,107,72,73],
	'RMUX14':[173,139,174,175,140,141],
	'RMUX15':[241,207,242,243,208,209],
	'RMUX16':[654,620,653,652,619,618],
	'RMUX17':[586,552,585,584,551,550],
	'RMUX18':[518,484,517,516,483,482],
	'RMUX19':[450,416,449,448,415,414],
	'RMUX20':[42,8,41,40,7,6],
	'RMUX21':[110,76,109,108,75,74],
	'RMUX22':[178,144,177,176,143,142],
	'RMUX23':[246,212,245,244,211,210],
	'RMUX24':[655,621,656,657,622,623],
	'RMUX25':[587,553,588,589,554,555],
	'RMUX26':[519,485,520,521,486,487],
	'RMUX27':[451,417,452,453,418,419],
	'RMUX28':[43,9,44,45,10,11],
	'RMUX29':[111,77,112,113,78,79],
	'RMUX30':[179,145,180,181,146,147],
	'RMUX31':[247,213,248,249,214,215],

	'SeamMUX00':[389,390,391,392,393,394,395,396],
	'SeamMUX01':[287,288,289,290,291,292,293,294],
	'SeamMUX02':[355,356,357,358,359,360,361,362],
	'SeamMUX03':[321,322,323,324,325,326,327,328],
	'SeamMUX04':[397,398,399,400,401,402,436,435],
	'SeamMUX05':[295,296,297,298,299,300,266,265],
	'SeamMUX06':[363,364,365,366,367,368,470,469],
	'SeamMUX07':[329,330,331,332,333,334,232,231],

	'TileClkMUX00':[405,404,439],
	'TileClkMUX01':[303,302,269],
	'TileClkMUX02':[371,370,438],
	'TileClkMUX03':[337,336,268],
	'TileClkMUX04':[406,407,440],
	'TileClkMUX05':[304,305,270],
	'TileClkMUX06':[372,373,441],
	'TileClkMUX07':[338,339,271],
}, formatters={
	'RMUX[0-9][0-9]': lambda key,val: mux_format(val, 3, 'I'),
	'IOMUX[0-9][0-9]': lambda key,val: mux_format(val, 4, 'I'),
	'TileClkMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 3, True),
	'CtrlMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 6, True),
	'GclkDMUX00': lambda key,val: bits_to_string(bits_invert(val), 6, True),
}, key_transformers={
    'alta_rio[0-9][0-9].[A-Z]*_USED': lambda x: None,
}, encoders={
	'CtrlMUX[0-9][0-9]': lambda key,val: mux_encode(val, 8, 4),
	'RMUX[0-9][0-9]': lambda key,val: mux_encode(val, 3, 3),
	'IOMUX[0-9][0-9]': lambda key,val: mux_encode(val, 4, 3),
	'TileClkMUX[0-9][0-9]': lambda key,val: mux_encode(val, 2, 1),
    'GclkDMUX00': lambda key,val: bits_invert(([0] * (4 - len(val))) + val),
}, defaults={
	'TileClkMUX[0-9][0-9]': [0,0,1],
	'IOMUX[0-9][0-9]': [0, 0, 0, 0, 0, 0, 1],
}))

InstallTile(Tile('AG1200_IOTILE_S4', 'IOTILE', columns=34, rows=20, slices=4, values={
	# Each CtrlMUX contains 2 entries of 6 bits each
	'CtrlMUX00': [ 376, 342, 375, 341, 374, 340, 308, 274, 307, 273, 306, 272 ],
	'CtrlMUX01': [ 382, 348, 381, 347, 380, 346, 314, 280, 313, 279, 312, 278 ],
	'CtrlMUX02': [ 377, 343, 378, 344, 379, 345, 309, 275, 310, 276, 311, 277 ],
	'CtrlMUX03': [ 383, 349, 384, 350, 385, 351, 315, 281, 316, 282, 317, 283 ],

	'InputMUX00':[679],
	'InputMUX01':[577],
	'InputMUX02':[543],
	'InputMUX03':[475],
	'InputMUX04':[33],
	'InputMUX05':[135],
	'InputMUX06':[169],
	'InputMUX07':[237],

	'IOMUX00':[664,630,663,629,662,628,627],
	'IOMUX01':[596,562,595,561,594,560,559],
	'IOMUX02':[52,18,51,17,50,16,15],
	'IOMUX03':[120,86,119,85,118,84,83],
	'IOMUX04':[528,494,527,493,526,492,491],
	'IOMUX05':[460,426,459,425,458,424,423],
	'IOMUX06':[188,154,187,153,186,152,151],
	'IOMUX07':[256,222,255,221,254,220,219],
	'IOMUX08':[529,495,530,496,531,497,498],
	'IOMUX09':[461,427,462,428,463,429,430],
	'IOMUX10':[189,155,190,156,191,157,158],
	'IOMUX11':[257,223,258,224,259,225,226],
	'IOMUX12':[665,631,666,632,667,633,634],
	'IOMUX13':[597,563,598,564,599,565,566],
	'IOMUX14':[53,19,54,20,55,21,22],
	'IOMUX15':[121,87,122,88,123,89,90],
	'IOMUX16':[672,638,671,637,670,636,635],
	'IOMUX17':[604,570,603,569,602,568,567],
	'IOMUX18':[60,26,59,25,58,24,23],
	'IOMUX19':[128,94,127,93,126,92,91],
	'IOMUX20':[536,502,535,501,534,500,499],
	'IOMUX21':[468,434,467,433,466,432,431],
	'IOMUX22':[196,162,195,161,194,160,159],
	'IOMUX23':[264,230,263,229,262,228,227],

	# Each of these contains 4 entries of 1 bit each
	'IN_ASYNC_MODE': [ 674, 677, 28, 31 ],
	'IN_POWERUP': [ 639, 644, 61, 66 ],
	'IN_SYNC_MODE': [ 673, 678, 27, 32 ],
	'OE_ASYNC_MODE': [ 538, 541, 164, 167 ],
	'OE_POWERUP': [ 503, 508, 197, 202 ],
	'OE_REG_MODE': [ 572, 575, 130, 133 ],
	'OE_SYNC_MODE': [ 537, 542, 163, 168 ],
	'OUT_ASYNC_MODE': [ 606, 609, 96, 99 ],
	'OUT_POWERUP': [ 571, 576, 129, 134 ],
	'OUT_REG_MODE': [ 504, 507, 198, 201 ],
	'OUT_SYNC_MODE': [ 605, 610, 95, 100 ],

	'RMUX00':[648,614,647,646,613,612],
	'RMUX01':[580,546,579,578,545,544],
	'RMUX02':[512,478,511,510,477,476],
	'RMUX03':[444,410,443,442,409,408],
	'RMUX04':[36,2,35,34,1,0],
	'RMUX05':[104,70,103,102,69,68],
	'RMUX06':[172,138,171,170,137,136],
	'RMUX07':[240,206,239,238,205,204],
	'RMUX08':[649,615,650,651,616,617],
	'RMUX09':[581,547,582,583,548,549],
	'RMUX10':[513,479,514,515,480,481],
	'RMUX11':[445,411,446,447,412,413],
	'RMUX12':[37,3,38,39,4,5],
	'RMUX13':[105,71,106,107,72,73],
	'RMUX14':[173,139,174,175,140,141],
	'RMUX15':[241,207,242,243,208,209],
	'RMUX16':[654,620,653,652,619,618],
	'RMUX17':[586,552,585,584,551,550],
	'RMUX18':[518,484,517,516,483,482],
	'RMUX19':[450,416,449,448,415,414],
	'RMUX20':[42,8,41,40,7,6],
	'RMUX21':[110,76,109,108,75,74],
	'RMUX22':[178,144,177,176,143,142],
	'RMUX23':[246,212,245,244,211,210],
	'RMUX24':[655,621,656,657,622,623],
	'RMUX25':[587,553,588,589,554,555],
	'RMUX26':[519,485,520,521,486,487],
	'RMUX27':[451,417,452,453,418,419],
	'RMUX28':[43,9,44,45,10,11],
	'RMUX29':[111,77,112,113,78,79],
	'RMUX30':[179,145,180,181,146,147],
	'RMUX31':[247,213,248,249,214,215],

	'SeamMUX00':[389,390,391,392,393,394,395,396],
	'SeamMUX01':[287,288,289,290,291,292,293,294],
	'SeamMUX02':[355,356,357,358,359,360,361,362],
	'SeamMUX03':[321,322,323,324,325,326,327,328],
	'SeamMUX04':[397,398,399,400,401,402,436,435],
	'SeamMUX05':[295,296,297,298,299,300,266,265],
	'SeamMUX06':[363,364,365,366,367,368,470,469],
	'SeamMUX07':[329,330,331,332,333,334,232,231],

	'TileClkMUX00':[405,404,439],
	'TileClkMUX01':[303,302,269],
	'TileClkMUX02':[371,370,438],
	'TileClkMUX03':[337,336,268],
	'TileClkMUX04':[406,407,440],
	'TileClkMUX05':[304,305,270],
	'TileClkMUX06':[372,373,441],
	'TileClkMUX07':[338,339,271],
}, formatters={
	'RMUX[0-9][0-9]': lambda key,val: mux_format(val, 3, 'I'),
	'IOMUX[0-9][0-9]': lambda key,val: mux_format(val, 4, 'I'),
	'TileClkMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 3, True),
	'SeamMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 8, True),
	'CtrlMUX[0-9][0-9]': lambda key,val: bits_to_string(val, 6, True)
}, key_transformers={
    'alta_rio[0-9][0-9].[A-Z]*_USED': lambda x: None,
}, encoders={
	'CtrlMUX[0-9][0-9]': lambda key,val: mux_encode(val, 8, 4),
	'RMUX[0-9][0-9]': lambda key,val: mux_encode(val, 3, 3),
	'IOMUX[0-9][0-9]': lambda key,val: mux_encode(val, 4, 3),
	'TileClkMUX[0-9][0-9]': lambda key,val: mux_encode(val, 2, 1),
}, defaults={
	'TileClkMUX[0-9][0-9]': [0,0,1],
	'IOMUX[0-9][0-9]': [0, 0, 0, 0, 0, 0, 1],
}))

InstallTile(Tile('ALTA_EMB4K5', 'BramTILE', columns=108, rows=68, slices=0, values={
	'BramClkMUX00': [ 3489, 3490, 3491, 3488 ], # alta_bram00:Clk0
	'BramClkMUX01': [ 3813, 3814, 3815, 3812 ], # alta_bram00:Clk1

	'CLKMODE': [ 3703 ],

	'CtrlMUX00':[3472,3580,3473,3581,3474,3582,3475,3583,3585,3584,3477,3476],   # BramClkMUX00 | TileWeRenMUX00
	'CtrlMUX01':[3483,3591,3482,3590,3481,3589,3480,3588,3586,3587,3478,3479],   # BramClkMUX01 | TileWeRenMUX01
	'CtrlMUX02':[3796,3688,3797,3689,3798,3690,3799,3691,3693,3692,3801,3800],   # TileAsyncMUX00 | TileClkEnMUX00
	'CtrlMUX03':[3807,3699,3806,3698,3805,3697,3804,3696,3694,3695,3802,3803],   # TileAsyncMUX01 | TileClkEnMUX01

	'DWSEL_A0': [ 1542, 462, 1326, 570 ],
	'DWSEL_B0': [ 5754, 6834, 5970, 6726 ],

	'IMUX00':[16,124,17,125,18,126,19,127,20,21,129,128],       # AddressA[0]
	'IMUX01':[27,135,26,134,25,133,24,132,23,22,130,131],       # AddressA[1]
	'IMUX02':[232,340,233,341,234,342,235,343,236,237,345,344], # AddressA[2]
	'IMUX03':[243,351,242,350,241,349,240,348,239,238,346,347], # AddressA[3]
	'IMUX04':[448,556,449,557,450,558,451,559,452,453,561,560], # AddressA[4]
	'IMUX05':[459,567,458,566,457,565,456,564,455,454,562,563], # AddressA[5]
	'IMUX06':[664,772,665,773,666,774,667,775,668,669,777,776], # AddressA[6]
	'IMUX07':[675,783,674,782,673,781,672,780,671,670,778,779], # AddressA[7]
	'IMUX08':[880,988,881,989,882,990,883,991,884,885,993,992], # AddressA[8]
	'IMUX09':[891,999,890,998,889,997,888,996,887,886,994,995], # AddressA[9]
	'IMUX10':[1096,1204,1097,1205,1098,1206,1099,1207,1100,1101,1209,1208], # AddressA[10]
	'IMUX11':[1107,1215,1106,1214,1105,1213,1104,1212,1103,1102,1210,1211], # AddressA[11]
	'IMUX12':[1312,1420,1313,1421,1314,1422,1315,1423,1316,1317,1425,1424], # DataInA[0]
	'IMUX13':[1323,1431,1322,1430,1321,1429,1320,1428,1319,1318,1426,1427], # DataInA[1]
	'IMUX14':[1528,1636,1529,1637,1530,1638,1531,1639,1532,1533,1641,1640], # DataInA[2]
	'IMUX15':[1539,1647,1538,1646,1537,1645,1536,1644,1535,1534,1642,1643], # DataInA[3]
	'IMUX16':[1744,1852,1745,1853,1746,1854,1747,1855,1748,1749,1857,1856], # DataInA[4]
	'IMUX17':[1755,1863,1754,1862,1753,1861,1752,1860,1751,1750,1858,1859], # DataInA[5]
	'IMUX18':[1960,2068,1961,2069,1962,2070,1963,2071,1964,1965,2073,2072], # DataInA[6]
	'IMUX19':[1971,2079,1970,2078,1969,2077,1968,2076,1967,1966,2074,2075], # DataInA[7]
	'IMUX20':[2176,2284,2177,2285,2178,2286,2179,2287,2180,2181,2289,2288], # DataInA[8]
	'IMUX21':[2187,2295,2186,2294,2185,2293,2184,2292,2183,2182,2290,2291], # DataInA[9]
	'IMUX22':[2392,2500,2393,2501,2394,2502,2395,2503,2396,2397,2505,2504], # DataInA[10]
	'IMUX23':[2403,2511,2402,2510,2401,2509,2400,2508,2399,2398,2506,2507], # DataInA[11]
	'IMUX24':[2608,2716,2609,2717,2610,2718,2611,2719,2612,2613,2721,2720], # DataInA[12]
	'IMUX25':[2619,2727,2618,2726,2617,2725,2616,2724,2615,2614,2722,2723], # DataInA[13]
	'IMUX26':[2824,2932,2825,2933,2826,2934,2827,2935,2828,2829,2937,2936], # DataInA[14]
	'IMUX27':[2835,2943,2834,2942,2833,2941,2832,2940,2831,2830,2938,2939], # DataInA[15]
	'IMUX28':[3040,3148,3041,3149,3042,3150,3043,3151,3044,3045,3153,3152], # DataInA[16]
	'IMUX29':[3051,3159,3050,3158,3049,3157,3048,3156,3047,3046,3154,3155], # DataInA[17]
	'IMUX30':[3256,3364,3257,3365,3258,3366,3259,3367,3260,3261,3369,3368], # BramClkMUX00 | TileWeRenMUX00
	'IMUX31':[3267,3375,3266,3374,3265,3373,3264,3372,3263,3262,3370,3371], # BramClkMUX01 | TileWeRenMUX01
	'IMUX32':[3904,4012,3905,4013,3906,4014,3907,4015,3908,3909,4017,4016], # TileAsyncMUX00 | TileClkEnMUX00
	'IMUX33':[3915,4023,3914,4022,3913,4021,3912,4020,3911,3910,4018,4019], # TileAsyncMUX01 | TileClkEnMUX01
	'IMUX34':[4120,4228,4121,4229,4122,4230,4123,4231,4124,4125,4233,4232], # DataInB[]
	'IMUX35':[4131,4239,4130,4238,4129,4237,4128,4236,4127,4126,4234,4235], # DataInB[]
	'IMUX36':[4336,4444,4337,4445,4338,4446,4339,4447,4340,4341,4449,4448], # DataInB[]
	'IMUX37':[4347,4455,4346,4454,4345,4453,4344,4452,4343,4342,4450,4451], # DataInB[]
	'IMUX38':[4552,4660,4553,4661,4554,4662,4555,4663,4556,4557,4665,4664], # DataInB[]
	'IMUX39':[4563,4671,4562,4670,4561,4669,4560,4668,4559,4558,4666,4667], # DataInB[]
	'IMUX40':[4768,4876,4769,4877,4770,4878,4771,4879,4772,4773,4881,4880], # DataInB[]
	'IMUX41':[4779,4887,4778,4886,4777,4885,4776,4884,4775,4774,4882,4883], # DataInB[]
	'IMUX42':[4984,5092,4985,5093,4986,5094,4987,5095,4988,4989,5097,5096], # DataInB[]
	'IMUX43':[4995,5103,4994,5102,4993,5101,4992,5100,4991,4990,5098,5099], # DataInB[]
	'IMUX44':[5200,5308,5201,5309,5202,5310,5203,5311,5204,5205,5313,5312], # DataInB[]
	'IMUX45':[5211,5319,5210,5318,5209,5317,5208,5316,5207,5206,5314,5315], # DataInB[]
	'IMUX46':[5416,5524,5417,5525,5418,5526,5419,5527,5420,5421,5529,5528], # DataInB[]
	'IMUX47':[5427,5535,5426,5534,5425,5533,5424,5532,5423,5422,5530,5531], # DataInB[]
	'IMUX48':[5632,5740,5633,5741,5634,5742,5635,5743,5636,5637,5745,5744], # DataInB[]
	'IMUX49':[5643,5751,5642,5750,5641,5749,5640,5748,5639,5638,5746,5747], # DataInB[]
	'IMUX50':[5848,5956,5849,5957,5850,5958,5851,5959,5852,5853,5961,5960], # DataInB[]
	'IMUX51':[5859,5967,5858,5966,5857,5965,5856,5964,5855,5854,5962,5963], # DataInB[]
	'IMUX52':[6064,6172,6065,6173,6066,6174,6067,6175,6068,6069,6177,6176], # AddressB[11]
	'IMUX53':[6075,6183,6074,6182,6073,6181,6072,6180,6071,6070,6178,6179], # AddressB[10]
	'IMUX54':[6280,6388,6281,6389,6282,6390,6283,6391,6284,6285,6393,6392], # AddressB[9]
	'IMUX55':[6291,6399,6290,6398,6289,6397,6288,6396,6287,6286,6394,6395], # AddressB[8]
	'IMUX56':[6496,6604,6497,6605,6498,6606,6499,6607,6500,6501,6609,6608], # AddressB[7]
	'IMUX57':[6507,6615,6506,6614,6505,6613,6504,6612,6503,6502,6610,6611], # AddressB[6]
	'IMUX58':[6712,6820,6713,6821,6714,6822,6715,6823,6716,6717,6825,6824], # AddressB[5]
	'IMUX59':[6723,6831,6722,6830,6721,6829,6720,6828,6719,6718,6826,6827], # AddressB[4]
	'IMUX60':[6928,7036,6929,7037,6930,7038,6931,7039,6932,6933,7041,7040], # AddressB[3]
	'IMUX61':[6939,7047,6938,7046,6937,7045,6936,7044,6935,6934,7042,7043], # AddressB[2]
	'IMUX62':[7144,7252,7145,7253,7146,7254,7147,7255,7148,7149,7257,7256], # AddressB[1]
	'IMUX63':[7155,7263,7154,7262,7153,7261,7152,7260,7151,7150,7258,7259], # AddressB[0]

	'RMUX00':[5,113,4,112,3,111,2,1,109,110],
	'RMUX01':[869,977,868,976,867,975,866,865,973,974],
	'RMUX02':[6,114,7,115,8,116,9,10,118,117],
	'RMUX03':[870,978,871,979,872,980,873,874,982,981],
	'RMUX04':[15,123,14,122,13,121,12,11,119,120],
	'RMUX05':[879,987,878,986,877,985,876,875,983,984],
	'RMUX06':[221,329,220,328,219,327,218,217,325,326],
	'RMUX07':[1085,1193,1084,1192,1083,1191,1082,1081,1189,1190],
	'RMUX08':[222,330,223,331,224,332,225,226,334,333],
	'RMUX09':[1086,1194,1087,1195,1088,1196,1089,1090,1198,1197],
	'RMUX10':[231,339,230,338,229,337,228,227,335,336],
	'RMUX11':[1095,1203,1094,1202,1093,1201,1092,1091,1199,1200],
	'RMUX12':[1302,1410,1303,1411,1304,1412,1305,1306,1414,1413],
	'RMUX13':[438,546,439,547,440,548,441,442,550,549],
	'RMUX14':[1311,1419,1310,1418,1309,1417,1308,1307,1415,1416],
	'RMUX15':[447,555,446,554,445,553,444,443,551,552],
	'RMUX16':[1301,1409,1300,1408,1299,1407,1298,1297,1405,1406],
	'RMUX17':[437,545,436,544,435,543,434,433,541,542],
	'RMUX18':[1518,1626,1519,1627,1520,1628,1521,1522,1630,1629],
	'RMUX19':[654,762,655,763,656,764,657,658,766,765],
	'RMUX20':[1527,1635,1526,1634,1525,1633,1524,1523,1631,1632],
	'RMUX21':[663,771,662,770,661,769,660,659,767,768],
	'RMUX22':[1517,1625,1516,1624,1515,1623,1514,1513,1621,1622],
	'RMUX23':[653,761,652,760,651,759,650,649,757,758],
	'RMUX24':[1733,1841,1732,1840,1731,1839,1730,1729,1837,1838],
	'RMUX25':[2597,2705,2596,2704,2595,2703,2594,2593,2701,2702],
	'RMUX26':[1734,1842,1735,1843,1736,1844,1737,1738,1846,1845],
	'RMUX27':[2598,2706,2599,2707,2600,2708,2601,2602,2710,2709],
	'RMUX28':[1743,1851,1742,1850,1741,1849,1740,1739,1847,1848],
	'RMUX29':[2607,2715,2606,2714,2605,2713,2604,2603,2711,2712],
	'RMUX30':[1949,2057,1948,2056,1947,2055,1946,1945,2053,2054],
	'RMUX31':[2813,2921,2812,2920,2811,2919,2810,2809,2917,2918],
	'RMUX32':[1950,2058,1951,2059,1952,2060,1953,1954,2062,2061],
	'RMUX33':[2814,2922,2815,2923,2816,2924,2817,2818,2926,2925],
	'RMUX34':[1959,2067,1958,2066,1957,2065,1956,1955,2063,2064],
	'RMUX35':[2823,2931,2822,2930,2821,2929,2820,2819,2927,2928],
	'RMUX36':[3030,3138,3031,3139,3032,3140,3033,3034,3142,3141],
	'RMUX37':[2166,2274,2167,2275,2168,2276,2169,2170,2278,2277],
	'RMUX38':[3039,3147,3038,3146,3037,3145,3036,3035,3143,3144],
	'RMUX39':[2175,2283,2174,2282,2173,2281,2172,2171,2279,2280],
	'RMUX40':[3029,3137,3028,3136,3027,3135,3026,3025,3133,3134],
	'RMUX41':[2165,2273,2164,2272,2163,2271,2162,2161,2269,2270],
	'RMUX42':[3246,3354,3247,3355,3248,3356,3249,3250,3358,3357],
	'RMUX43':[2382,2490,2383,2491,2384,2492,2385,2386,2494,2493],
	'RMUX44':[3255,3363,3254,3362,3253,3361,3252,3251,3359,3360],
	'RMUX45':[2391,2499,2390,2498,2389,2497,2388,2387,2495,2496],
	'RMUX46':[3245,3353,3244,3352,3243,3351,3242,3241,3349,3350],
	'RMUX47':[2381,2489,2380,2488,2379,2487,2378,2377,2485,2486],
	'RMUX48':[3893,4001,3892,4000,3891,3999,3890,3889,3997,3998],
	'RMUX49':[4757,4865,4756,4864,4755,4863,4754,4753,4861,4862],
	'RMUX50':[3894,4002,3895,4003,3896,4004,3897,3898,4006,4005],
	'RMUX51':[4758,4866,4759,4867,4760,4868,4761,4762,4870,4869],
	'RMUX52':[3903,4011,3902,4010,3901,4009,3900,3899,4007,4008],
	'RMUX53':[4767,4875,4766,4874,4765,4873,4764,4763,4871,4872],
	'RMUX54':[4109,4217,4108,4216,4107,4215,4106,4105,4213,4214],
	'RMUX55':[4973,5081,4972,5080,4971,5079,4970,4969,5077,5078],
	'RMUX56':[4110,4218,4111,4219,4112,4220,4113,4114,4222,4221],
	'RMUX57':[4974,5082,4975,5083,4976,5084,4977,4978,5086,5085],
	'RMUX58':[4119,4227,4118,4226,4117,4225,4116,4115,4223,4224],
	'RMUX59':[4983,5091,4982,5090,4981,5089,4980,4979,5087,5088],
	'RMUX60':[5190,5298,5191,5299,5192,5300,5193,5194,5302,5301],
	'RMUX61':[4326,4434,4327,4435,4328,4436,4329,4330,4438,4437],
	'RMUX62':[5199,5307,5198,5306,5197,5305,5196,5195,5303,5304],
	'RMUX63':[4335,4443,4334,4442,4333,4441,4332,4331,4439,4440],
	'RMUX64':[5189,5297,5188,5296,5187,5295,5186,5185,5293,5294],
	'RMUX65':[4325,4433,4324,4432,4323,4431,4322,4321,4429,4430],
	'RMUX66':[5406,5514,5407,5515,5408,5516,5409,5410,5518,5517],
	'RMUX67':[4542,4650,4543,4651,4544,4652,4545,4546,4654,4653],
	'RMUX68':[5415,5523,5414,5522,5413,5521,5412,5411,5519,5520],
	'RMUX69':[4551,4659,4550,4658,4549,4657,4548,4547,4655,4656],
	'RMUX70':[5405,5513,5404,5512,5403,5511,5402,5401,5509,5510],
	'RMUX71':[4541,4649,4540,4648,4539,4647,4538,4537,4645,4646],
	'RMUX72':[5621,5729,5620,5728,5619,5727,5618,5617,5725,5726],
	'RMUX73':[6485,6593,6484,6592,6483,6591,6482,6481,6589,6590],
	'RMUX74':[5622,5730,5623,5731,5624,5732,5625,5626,5734,5733],
	'RMUX75':[6486,6594,6487,6595,6488,6596,6489,6490,6598,6597],
	'RMUX76':[5631,5739,5630,5738,5629,5737,5628,5627,5735,5736],
	'RMUX77':[6495,6603,6494,6602,6493,6601,6492,6491,6599,6600],
	'RMUX78':[5837,5945,5836,5944,5835,5943,5834,5833,5941,5942],
	'RMUX79':[6701,6809,6700,6808,6699,6807,6698,6697,6805,6806],
	'RMUX80':[5838,5946,5839,5947,5840,5948,5841,5842,5950,5949],
	'RMUX81':[6702,6810,6703,6811,6704,6812,6705,6706,6814,6813],
	'RMUX82':[5847,5955,5846,5954,5845,5953,5844,5843,5951,5952],
	'RMUX83':[6711,6819,6710,6818,6709,6817,6708,6707,6815,6816],
	'RMUX84':[6918,7026,6919,7027,6920,7028,6921,6922,7030,7029],
	'RMUX85':[6054,6162,6055,6163,6056,6164,6057,6058,6166,6165],
	'RMUX86':[6927,7035,6926,7034,6925,7033,6924,6923,7031,7032],
	'RMUX87':[6063,6171,6062,6170,6061,6169,6060,6059,6167,6168],
	'RMUX88':[6917,7025,6916,7024,6915,7023,6914,6913,7021,7022],
	'RMUX89':[6053,6161,6052,6160,6051,6159,6050,6049,6157,6158],
	'RMUX90':[7134,7242,7135,7243,7136,7244,7137,7138,7246,7245],
	'RMUX91':[6270,6378,6271,6379,6272,6380,6273,6274,6382,6381],
	'RMUX92':[7143,7251,7142,7250,7141,7249,7140,7139,7247,7248],
	'RMUX93':[6279,6387,6278,6386,6277,6385,6276,6275,6383,6384],
	'RMUX94':[7133,7241,7132,7240,7131,7239,7130,7129,7237,7238],
	'RMUX95':[6269,6377,6268,6376,6267,6375,6266,6265,6373,6374],

	'SeamMUX00':[3457,3458,3459,3460,3461,3462,3463,3464],   # IsoMUXPseudo00 | BramClkMUX00
	'SeamMUX01':[3781,3782,3783,3784,3785,3786,3787,3788],   # IsoMUXPseudo01 | BramClkMUX01
	'SeamMUX02':[3465,3466,3578,3467,3468,3469,3470,3471],   # IsoMUXPseudo02 | TileAsyncMUX00
	'SeamMUX03':[3789,3790,3686,3791,3792,3793,3794,3795],   # IsoMUXPseudo03 | TileAsyncMUX01
	'SeamMUX04':[2592,2700,2808,2916,3024,3132,3240,3348],   # TileWeRenMUX00 
	'SeamMUX05':[4644,4536,4428,4320,4212,4104,3996,3888],   # TileWeRenMUX01

	'SELOUT_A': [ 30 ],
	'SELOUT_B': [ 7266 ],
	'SEL_PORTMODE': [ 3918 ],
	'SEL_WKMODE_A': [ 1866 ],
	'SEL_WKMODE_B': [ 5430 ],
	'SEL_WRTHU_A': [ 3270 ],
	'SEL_WRTHU_B': [ 4026 ],

	'TileAsyncMUX00':[3486,3485,3484,3487],  # alta_bram00:AsyncReset0
	'TileAsyncMUX01':[3810,3809,3808,3811],  # alta_bram00:AsyncReset1

	'TileClkEnMUX00':[3593,3592,3594],   # alta_bram00:ClkEn0
	'TileClkEnMUX01':[3701,3700,3702],   # alta_bram00:ClkEn1

	'TileWeRenMUX00':[3597,3598,3599,3596],  # alta_bram00:WeRenA
	'TileWeRenMUX01':[3705,3706,3707,3704],  # alta_bram00:WeRenB

	# INIT_VAL contains 4608 bits 
	# Value appears backwards from how it is supplied in Verilog
	'INIT_VAL': [ 36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104, 37, 41, 45, 49, 53, 57, 61, 65, 69, 73, 77, 81, 85, 89, 93, 97, 101, 105, 38, 42, 46, 50, 54, 58, 62, 66, 70, 74, 78, 82, 86, 90, 94, 98, 102, 106, 39, 43, 47, 51, 55, 59, 63, 67, 71, 75, 79, 83, 87, 91, 95, 99, 103, 107, 144, 148, 152, 156, 160, 164, 168, 172, 176, 180, 184, 188, 192, 196, 200, 204, 208, 212, 145, 149, 153, 157, 161, 165, 169, 173, 177, 181, 185, 189, 193, 197, 201, 205, 209, 213, 146, 150, 154, 158, 162, 166, 170, 174, 178, 182, 186, 190, 194, 198, 202, 206, 210, 214, 147, 151, 155, 159, 163, 167, 171, 175, 179, 183, 187, 191, 195, 199, 203, 207, 211, 215, 252, 256, 260, 264, 268, 272, 276, 280, 284, 288, 292, 296, 300, 304, 308, 312, 316, 320, 253, 257, 261, 265, 269, 273, 277, 281, 285, 289, 293, 297, 301, 305, 309, 313, 317, 321, 254, 258, 262, 266, 270, 274, 278, 282, 286, 290, 294, 298, 302, 306, 310, 314, 318, 322, 255, 259, 263, 267, 271, 275, 279, 283, 287, 291, 295, 299, 303, 307, 311, 315, 319, 323, 360, 364, 368, 372, 376, 380, 384, 388, 392, 396, 400, 404, 408, 412, 416, 420, 424, 428, 361, 365, 369, 373, 377, 381, 385, 389, 393, 397, 401, 405, 409, 413, 417, 421, 425, 429, 362, 366, 370, 374, 378, 382, 386, 390, 394, 398, 402, 406, 410, 414, 418, 422, 426, 430, 363, 367, 371, 375, 379, 383, 387, 391, 395, 399, 403, 407, 411, 415, 419, 423, 427, 431, 468, 472, 476, 480, 484, 488, 492, 496, 500, 504, 508, 512, 516, 520, 524, 528, 532, 536, 469, 473, 477, 481, 485, 489, 493, 497, 501, 505, 509, 513, 517, 521, 525, 529, 533, 537, 470, 474, 478, 482, 486, 490, 494, 498, 502, 506, 510, 514, 518, 522, 526, 530, 534, 538, 471, 475, 479, 483, 487, 491, 495, 499, 503, 507, 511, 515, 519, 523, 527, 531, 535, 539, 576, 580, 584, 588, 592, 596, 600, 604, 608, 612, 616, 620, 624, 628, 632, 636, 640, 644, 577, 581, 585, 589, 593, 597, 601, 605, 609, 613, 617, 621, 625, 629, 633, 637, 641, 645, 578, 582, 586, 590, 594, 598, 602, 606, 610, 614, 618, 622, 626, 630, 634, 638, 642, 646, 579, 583, 587, 591, 595, 599, 603, 607, 611, 615, 619, 623, 627, 631, 635, 639, 643, 647, 684, 688, 692, 696, 700, 704, 708, 712, 716, 720, 724, 728, 732, 736, 740, 744, 748, 752, 685, 689, 693, 697, 701, 705, 709, 713, 717, 721, 725, 729, 733, 737, 741, 745, 749, 753, 686, 690, 694, 698, 702, 706, 710, 714, 718, 722, 726, 730, 734, 738, 742, 746, 750, 754, 687, 691, 695, 699, 703, 707, 711, 715, 719, 723, 727, 731, 735, 739, 743, 747, 751, 755, 792, 796, 800, 804, 808, 812, 816, 820, 824, 828, 832, 836, 840, 844, 848, 852, 856, 860, 793, 797, 801, 805, 809, 813, 817, 821, 825, 829, 833, 837, 841, 845, 849, 853, 857, 861, 794, 798, 802, 806, 810, 814, 818, 822, 826, 830, 834, 838, 842, 846, 850, 854, 858, 862, 795, 799, 803, 807, 811, 815, 819, 823, 827, 831, 835, 839, 843, 847, 851, 855, 859, 863, 900, 904, 908, 912, 916, 920, 924, 928, 932, 936, 940, 944, 948, 952, 956, 960, 964, 968, 901, 905, 909, 913, 917, 921, 925, 929, 933, 937, 941, 945, 949, 953, 957, 961, 965, 969, 902, 906, 910, 914, 918, 922, 926, 930, 934, 938, 942, 946, 950, 954, 958, 962, 966, 970, 903, 907, 911, 915, 919, 923, 927, 931, 935, 939, 943, 947, 951, 955, 959, 963, 967, 971, 1008, 1012, 1016, 1020, 1024, 1028, 1032, 1036, 1040, 1044, 1048, 1052, 1056, 1060, 1064, 1068, 1072, 1076, 1009, 1013, 1017, 1021, 1025, 1029, 1033, 1037, 1041, 1045, 1049, 1053, 1057, 1061, 1065, 1069, 1073, 1077, 1010, 1014, 1018, 1022, 1026, 1030, 1034, 1038, 1042, 1046, 1050, 1054, 1058, 1062, 1066, 1070, 1074, 1078, 1011, 1015, 1019, 1023, 1027, 1031, 1035, 1039, 1043, 1047, 1051, 1055, 1059, 1063, 1067, 1071, 1075, 1079, 1116, 1120, 1124, 1128, 1132, 1136, 1140, 1144, 1148, 1152, 1156, 1160, 1164, 1168, 1172, 1176, 1180, 1184, 1117, 1121, 1125, 1129, 1133, 1137, 1141, 1145, 1149, 1153, 1157, 1161, 1165, 1169, 1173, 1177, 1181, 1185, 1118, 1122, 1126, 1130, 1134, 1138, 1142, 1146, 1150, 1154, 1158, 1162, 1166, 1170, 1174, 1178, 1182, 1186, 1119, 1123, 1127, 1131, 1135, 1139, 1143, 1147, 1151, 1155, 1159, 1163, 1167, 1171, 1175, 1179, 1183, 1187, 1224, 1228, 1232, 1236, 1240, 1244, 1248, 1252, 1256, 1260, 1264, 1268, 1272, 1276, 1280, 1284, 1288, 1292, 1225, 1229, 1233, 1237, 1241, 1245, 1249, 1253, 1257, 1261, 1265, 1269, 1273, 1277, 1281, 1285, 1289, 1293, 1226, 1230, 1234, 1238, 1242, 1246, 1250, 1254, 1258, 1262, 1266, 1270, 1274, 1278, 1282, 1286, 1290, 1294, 1227, 1231, 1235, 1239, 1243, 1247, 1251, 1255, 1259, 1263, 1267, 1271, 1275, 1279, 1283, 1287, 1291, 1295, 1332, 1336, 1340, 1344, 1348, 1352, 1356, 1360, 1364, 1368, 1372, 1376, 1380, 1384, 1388, 1392, 1396, 1400, 1333, 1337, 1341, 1345, 1349, 1353, 1357, 1361, 1365, 1369, 1373, 1377, 1381, 1385, 1389, 1393, 1397, 1401, 1334, 1338, 1342, 1346, 1350, 1354, 1358, 1362, 1366, 1370, 1374, 1378, 1382, 1386, 1390, 1394, 1398, 1402, 1335, 1339, 1343, 1347, 1351, 1355, 1359, 1363, 1367, 1371, 1375, 1379, 1383, 1387, 1391, 1395, 1399, 1403, 1440, 1444, 1448, 1452, 1456, 1460, 1464, 1468, 1472, 1476, 1480, 1484, 1488, 1492, 1496, 1500, 1504, 1508, 1441, 1445, 1449, 1453, 1457, 1461, 1465, 1469, 1473, 1477, 1481, 1485, 1489, 1493, 1497, 1501, 1505, 1509, 1442, 1446, 1450, 1454, 1458, 1462, 1466, 1470, 1474, 1478, 1482, 1486, 1490, 1494, 1498, 1502, 1506, 1510, 1443, 1447, 1451, 1455, 1459, 1463, 1467, 1471, 1475, 1479, 1483, 1487, 1491, 1495, 1499, 1503, 1507, 1511, 1548, 1552, 1556, 1560, 1564, 1568, 1572, 1576, 1580, 1584, 1588, 1592, 1596, 1600, 1604, 1608, 1612, 1616, 1549, 1553, 1557, 1561, 1565, 1569, 1573, 1577, 1581, 1585, 1589, 1593, 1597, 1601, 1605, 1609, 1613, 1617, 1550, 1554, 1558, 1562, 1566, 1570, 1574, 1578, 1582, 1586, 1590, 1594, 1598, 1602, 1606, 1610, 1614, 1618, 1551, 1555, 1559, 1563, 1567, 1571, 1575, 1579, 1583, 1587, 1591, 1595, 1599, 1603, 1607, 1611, 1615, 1619, 1656, 1660, 1664, 1668, 1672, 1676, 1680, 1684, 1688, 1692, 1696, 1700, 1704, 1708, 1712, 1716, 1720, 1724, 1657, 1661, 1665, 1669, 1673, 1677, 1681, 1685, 1689, 1693, 1697, 1701, 1705, 1709, 1713, 1717, 1721, 1725, 1658, 1662, 1666, 1670, 1674, 1678, 1682, 1686, 1690, 1694, 1698, 1702, 1706, 1710, 1714, 1718, 1722, 1726, 1659, 1663, 1667, 1671, 1675, 1679, 1683, 1687, 1691, 1695, 1699, 1703, 1707, 1711, 1715, 1719, 1723, 1727, 1764, 1768, 1772, 1776, 1780, 1784, 1788, 1792, 1796, 1800, 1804, 1808, 1812, 1816, 1820, 1824, 1828, 1832, 1765, 1769, 1773, 1777, 1781, 1785, 1789, 1793, 1797, 1801, 1805, 1809, 1813, 1817, 1821, 1825, 1829, 1833, 1766, 1770, 1774, 1778, 1782, 1786, 1790, 1794, 1798, 1802, 1806, 1810, 1814, 1818, 1822, 1826, 1830, 1834, 1767, 1771, 1775, 1779, 1783, 1787, 1791, 1795, 1799, 1803, 1807, 1811, 1815, 1819, 1823, 1827, 1831, 1835, 1872, 1876, 1880, 1884, 1888, 1892, 1896, 1900, 1904, 1908, 1912, 1916, 1920, 1924, 1928, 1932, 1936, 1940, 1873, 1877, 1881, 1885, 1889, 1893, 1897, 1901, 1905, 1909, 1913, 1917, 1921, 1925, 1929, 1933, 1937, 1941, 1874, 1878, 1882, 1886, 1890, 1894, 1898, 1902, 1906, 1910, 1914, 1918, 1922, 1926, 1930, 1934, 1938, 1942, 1875, 1879, 1883, 1887, 1891, 1895, 1899, 1903, 1907, 1911, 1915, 1919, 1923, 1927, 1931, 1935, 1939, 1943, 1980, 1984, 1988, 1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020, 2024, 2028, 2032, 2036, 2040, 2044, 2048, 1981, 1985, 1989, 1993, 1997, 2001, 2005, 2009, 2013, 2017, 2021, 2025, 2029, 2033, 2037, 2041, 2045, 2049, 1982, 1986, 1990, 1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022, 2026, 2030, 2034, 2038, 2042, 2046, 2050, 1983, 1987, 1991, 1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023, 2027, 2031, 2035, 2039, 2043, 2047, 2051, 2088, 2092, 2096, 2100, 2104, 2108, 2112, 2116, 2120, 2124, 2128, 2132, 2136, 2140, 2144, 2148, 2152, 2156, 2089, 2093, 2097, 2101, 2105, 2109, 2113, 2117, 2121, 2125, 2129, 2133, 2137, 2141, 2145, 2149, 2153, 2157, 2090, 2094, 2098, 2102, 2106, 2110, 2114, 2118, 2122, 2126, 2130, 2134, 2138, 2142, 2146, 2150, 2154, 2158, 2091, 2095, 2099, 2103, 2107, 2111, 2115, 2119, 2123, 2127, 2131, 2135, 2139, 2143, 2147, 2151, 2155, 2159, 2196, 2200, 2204, 2208, 2212, 2216, 2220, 2224, 2228, 2232, 2236, 2240, 2244, 2248, 2252, 2256, 2260, 2264, 2197, 2201, 2205, 2209, 2213, 2217, 2221, 2225, 2229, 2233, 2237, 2241, 2245, 2249, 2253, 2257, 2261, 2265, 2198, 2202, 2206, 2210, 2214, 2218, 2222, 2226, 2230, 2234, 2238, 2242, 2246, 2250, 2254, 2258, 2262, 2266, 2199, 2203, 2207, 2211, 2215, 2219, 2223, 2227, 2231, 2235, 2239, 2243, 2247, 2251, 2255, 2259, 2263, 2267, 2304, 2308, 2312, 2316, 2320, 2324, 2328, 2332, 2336, 2340, 2344, 2348, 2352, 2356, 2360, 2364, 2368, 2372, 2305, 2309, 2313, 2317, 2321, 2325, 2329, 2333, 2337, 2341, 2345, 2349, 2353, 2357, 2361, 2365, 2369, 2373, 2306, 2310, 2314, 2318, 2322, 2326, 2330, 2334, 2338, 2342, 2346, 2350, 2354, 2358, 2362, 2366, 2370, 2374, 2307, 2311, 2315, 2319, 2323, 2327, 2331, 2335, 2339, 2343, 2347, 2351, 2355, 2359, 2363, 2367, 2371, 2375, 2412, 2416, 2420, 2424, 2428, 2432, 2436, 2440, 2444, 2448, 2452, 2456, 2460, 2464, 2468, 2472, 2476, 2480, 2413, 2417, 2421, 2425, 2429, 2433, 2437, 2441, 2445, 2449, 2453, 2457, 2461, 2465, 2469, 2473, 2477, 2481, 2414, 2418, 2422, 2426, 2430, 2434, 2438, 2442, 2446, 2450, 2454, 2458, 2462, 2466, 2470, 2474, 2478, 2482, 2415, 2419, 2423, 2427, 2431, 2435, 2439, 2443, 2447, 2451, 2455, 2459, 2463, 2467, 2471, 2475, 2479, 2483, 2520, 2524, 2528, 2532, 2536, 2540, 2544, 2548, 2552, 2556, 2560, 2564, 2568, 2572, 2576, 2580, 2584, 2588, 2521, 2525, 2529, 2533, 2537, 2541, 2545, 2549, 2553, 2557, 2561, 2565, 2569, 2573, 2577, 2581, 2585, 2589, 2522, 2526, 2530, 2534, 2538, 2542, 2546, 2550, 2554, 2558, 2562, 2566, 2570, 2574, 2578, 2582, 2586, 2590, 2523, 2527, 2531, 2535, 2539, 2543, 2547, 2551, 2555, 2559, 2563, 2567, 2571, 2575, 2579, 2583, 2587, 2591, 2628, 2632, 2636, 2640, 2644, 2648, 2652, 2656, 2660, 2664, 2668, 2672, 2676, 2680, 2684, 2688, 2692, 2696, 2629, 2633, 2637, 2641, 2645, 2649, 2653, 2657, 2661, 2665, 2669, 2673, 2677, 2681, 2685, 2689, 2693, 2697, 2630, 2634, 2638, 2642, 2646, 2650, 2654, 2658, 2662, 2666, 2670, 2674, 2678, 2682, 2686, 2690, 2694, 2698, 2631, 2635, 2639, 2643, 2647, 2651, 2655, 2659, 2663, 2667, 2671, 2675, 2679, 2683, 2687, 2691, 2695, 2699, 2736, 2740, 2744, 2748, 2752, 2756, 2760, 2764, 2768, 2772, 2776, 2780, 2784, 2788, 2792, 2796, 2800, 2804, 2737, 2741, 2745, 2749, 2753, 2757, 2761, 2765, 2769, 2773, 2777, 2781, 2785, 2789, 2793, 2797, 2801, 2805, 2738, 2742, 2746, 2750, 2754, 2758, 2762, 2766, 2770, 2774, 2778, 2782, 2786, 2790, 2794, 2798, 2802, 2806, 2739, 2743, 2747, 2751, 2755, 2759, 2763, 2767, 2771, 2775, 2779, 2783, 2787, 2791, 2795, 2799, 2803, 2807, 2844, 2848, 2852, 2856, 2860, 2864, 2868, 2872, 2876, 2880, 2884, 2888, 2892, 2896, 2900, 2904, 2908, 2912, 2845, 2849, 2853, 2857, 2861, 2865, 2869, 2873, 2877, 2881, 2885, 2889, 2893, 2897, 2901, 2905, 2909, 2913, 2846, 2850, 2854, 2858, 2862, 2866, 2870, 2874, 2878, 2882, 2886, 2890, 2894, 2898, 2902, 2906, 2910, 2914, 2847, 2851, 2855, 2859, 2863, 2867, 2871, 2875, 2879, 2883, 2887, 2891, 2895, 2899, 2903, 2907, 2911, 2915, 2952, 2956, 2960, 2964, 2968, 2972, 2976, 2980, 2984, 2988, 2992, 2996, 3000, 3004, 3008, 3012, 3016, 3020, 2953, 2957, 2961, 2965, 2969, 2973, 2977, 2981, 2985, 2989, 2993, 2997, 3001, 3005, 3009, 3013, 3017, 3021, 2954, 2958, 2962, 2966, 2970, 2974, 2978, 2982, 2986, 2990, 2994, 2998, 3002, 3006, 3010, 3014, 3018, 3022, 2955, 2959, 2963, 2967, 2971, 2975, 2979, 2983, 2987, 2991, 2995, 2999, 3003, 3007, 3011, 3015, 3019, 3023, 3060, 3064, 3068, 3072, 3076, 3080, 3084, 3088, 3092, 3096, 3100, 3104, 3108, 3112, 3116, 3120, 3124, 3128, 3061, 3065, 3069, 3073, 3077, 3081, 3085, 3089, 3093, 3097, 3101, 3105, 3109, 3113, 3117, 3121, 3125, 3129, 3062, 3066, 3070, 3074, 3078, 3082, 3086, 3090, 3094, 3098, 3102, 3106, 3110, 3114, 3118, 3122, 3126, 3130, 3063, 3067, 3071, 3075, 3079, 3083, 3087, 3091, 3095, 3099, 3103, 3107, 3111, 3115, 3119, 3123, 3127, 3131, 3168, 3172, 3176, 3180, 3184, 3188, 3192, 3196, 3200, 3204, 3208, 3212, 3216, 3220, 3224, 3228, 3232, 3236, 3169, 3173, 3177, 3181, 3185, 3189, 3193, 3197, 3201, 3205, 3209, 3213, 3217, 3221, 3225, 3229, 3233, 3237, 3170, 3174, 3178, 3182, 3186, 3190, 3194, 3198, 3202, 3206, 3210, 3214, 3218, 3222, 3226, 3230, 3234, 3238, 3171, 3175, 3179, 3183, 3187, 3191, 3195, 3199, 3203, 3207, 3211, 3215, 3219, 3223, 3227, 3231, 3235, 3239, 3276, 3280, 3284, 3288, 3292, 3296, 3300, 3304, 3308, 3312, 3316, 3320, 3324, 3328, 3332, 3336, 3340, 3344, 3277, 3281, 3285, 3289, 3293, 3297, 3301, 3305, 3309, 3313, 3317, 3321, 3325, 3329, 3333, 3337, 3341, 3345, 3278, 3282, 3286, 3290, 3294, 3298, 3302, 3306, 3310, 3314, 3318, 3322, 3326, 3330, 3334, 3338, 3342, 3346, 3279, 3283, 3287, 3291, 3295, 3299, 3303, 3307, 3311, 3315, 3319, 3323, 3327, 3331, 3335, 3339, 3343, 3347, 3384, 3388, 3392, 3396, 3400, 3404, 3408, 3412, 3416, 3420, 3424, 3428, 3432, 3436, 3440, 3444, 3448, 3452, 3385, 3389, 3393, 3397, 3401, 3405, 3409, 3413, 3417, 3421, 3425, 3429, 3433, 3437, 3441, 3445, 3449, 3453, 3386, 3390, 3394, 3398, 3402, 3406, 3410, 3414, 3418, 3422, 3426, 3430, 3434, 3438, 3442, 3446, 3450, 3454, 3387, 3391, 3395, 3399, 3403, 3407, 3411, 3415, 3419, 3423, 3427, 3431, 3435, 3439, 3443, 3447, 3451, 3455, 3924, 3928, 3932, 3936, 3940, 3944, 3948, 3952, 3956, 3960, 3964, 3968, 3972, 3976, 3980, 3984, 3988, 3992, 3925, 3929, 3933, 3937, 3941, 3945, 3949, 3953, 3957, 3961, 3965, 3969, 3973, 3977, 3981, 3985, 3989, 3993, 3926, 3930, 3934, 3938, 3942, 3946, 3950, 3954, 3958, 3962, 3966, 3970, 3974, 3978, 3982, 3986, 3990, 3994, 3927, 3931, 3935, 3939, 3943, 3947, 3951, 3955, 3959, 3963, 3967, 3971, 3975, 3979, 3983, 3987, 3991, 3995, 4032, 4036, 4040, 4044, 4048, 4052, 4056, 4060, 4064, 4068, 4072, 4076, 4080, 4084, 4088, 4092, 4096, 4100, 4033, 4037, 4041, 4045, 4049, 4053, 4057, 4061, 4065, 4069, 4073, 4077, 4081, 4085, 4089, 4093, 4097, 4101, 4034, 4038, 4042, 4046, 4050, 4054, 4058, 4062, 4066, 4070, 4074, 4078, 4082, 4086, 4090, 4094, 4098, 4102, 4035, 4039, 4043, 4047, 4051, 4055, 4059, 4063, 4067, 4071, 4075, 4079, 4083, 4087, 4091, 4095, 4099, 4103, 4140, 4144, 4148, 4152, 4156, 4160, 4164, 4168, 4172, 4176, 4180, 4184, 4188, 4192, 4196, 4200, 4204, 4208, 4141, 4145, 4149, 4153, 4157, 4161, 4165, 4169, 4173, 4177, 4181, 4185, 4189, 4193, 4197, 4201, 4205, 4209, 4142, 4146, 4150, 4154, 4158, 4162, 4166, 4170, 4174, 4178, 4182, 4186, 4190, 4194, 4198, 4202, 4206, 4210, 4143, 4147, 4151, 4155, 4159, 4163, 4167, 4171, 4175, 4179, 4183, 4187, 4191, 4195, 4199, 4203, 4207, 4211, 4248, 4252, 4256, 4260, 4264, 4268, 4272, 4276, 4280, 4284, 4288, 4292, 4296, 4300, 4304, 4308, 4312, 4316, 4249, 4253, 4257, 4261, 4265, 4269, 4273, 4277, 4281, 4285, 4289, 4293, 4297, 4301, 4305, 4309, 4313, 4317, 4250, 4254, 4258, 4262, 4266, 4270, 4274, 4278, 4282, 4286, 4290, 4294, 4298, 4302, 4306, 4310, 4314, 4318, 4251, 4255, 4259, 4263, 4267, 4271, 4275, 4279, 4283, 4287, 4291, 4295, 4299, 4303, 4307, 4311, 4315, 4319, 4356, 4360, 4364, 4368, 4372, 4376, 4380, 4384, 4388, 4392, 4396, 4400, 4404, 4408, 4412, 4416, 4420, 4424, 4357, 4361, 4365, 4369, 4373, 4377, 4381, 4385, 4389, 4393, 4397, 4401, 4405, 4409, 4413, 4417, 4421, 4425, 4358, 4362, 4366, 4370, 4374, 4378, 4382, 4386, 4390, 4394, 4398, 4402, 4406, 4410, 4414, 4418, 4422, 4426, 4359, 4363, 4367, 4371, 4375, 4379, 4383, 4387, 4391, 4395, 4399, 4403, 4407, 4411, 4415, 4419, 4423, 4427, 4464, 4468, 4472, 4476, 4480, 4484, 4488, 4492, 4496, 4500, 4504, 4508, 4512, 4516, 4520, 4524, 4528, 4532, 4465, 4469, 4473, 4477, 4481, 4485, 4489, 4493, 4497, 4501, 4505, 4509, 4513, 4517, 4521, 4525, 4529, 4533, 4466, 4470, 4474, 4478, 4482, 4486, 4490, 4494, 4498, 4502, 4506, 4510, 4514, 4518, 4522, 4526, 4530, 4534, 4467, 4471, 4475, 4479, 4483, 4487, 4491, 4495, 4499, 4503, 4507, 4511, 4515, 4519, 4523, 4527, 4531, 4535, 4572, 4576, 4580, 4584, 4588, 4592, 4596, 4600, 4604, 4608, 4612, 4616, 4620, 4624, 4628, 4632, 4636, 4640, 4573, 4577, 4581, 4585, 4589, 4593, 4597, 4601, 4605, 4609, 4613, 4617, 4621, 4625, 4629, 4633, 4637, 4641, 4574, 4578, 4582, 4586, 4590, 4594, 4598, 4602, 4606, 4610, 4614, 4618, 4622, 4626, 4630, 4634, 4638, 4642, 4575, 4579, 4583, 4587, 4591, 4595, 4599, 4603, 4607, 4611, 4615, 4619, 4623, 4627, 4631, 4635, 4639, 4643, 4680, 4684, 4688, 4692, 4696, 4700, 4704, 4708, 4712, 4716, 4720, 4724, 4728, 4732, 4736, 4740, 4744, 4748, 4681, 4685, 4689, 4693, 4697, 4701, 4705, 4709, 4713, 4717, 4721, 4725, 4729, 4733, 4737, 4741, 4745, 4749, 4682, 4686, 4690, 4694, 4698, 4702, 4706, 4710, 4714, 4718, 4722, 4726, 4730, 4734, 4738, 4742, 4746, 4750, 4683, 4687, 4691, 4695, 4699, 4703, 4707, 4711, 4715, 4719, 4723, 4727, 4731, 4735, 4739, 4743, 4747, 4751, 4788, 4792, 4796, 4800, 4804, 4808, 4812, 4816, 4820, 4824, 4828, 4832, 4836, 4840, 4844, 4848, 4852, 4856, 4789, 4793, 4797, 4801, 4805, 4809, 4813, 4817, 4821, 4825, 4829, 4833, 4837, 4841, 4845, 4849, 4853, 4857, 4790, 4794, 4798, 4802, 4806, 4810, 4814, 4818, 4822, 4826, 4830, 4834, 4838, 4842, 4846, 4850, 4854, 4858, 4791, 4795, 4799, 4803, 4807, 4811, 4815, 4819, 4823, 4827, 4831, 4835, 4839, 4843, 4847, 4851, 4855, 4859, 4896, 4900, 4904, 4908, 4912, 4916, 4920, 4924, 4928, 4932, 4936, 4940, 4944, 4948, 4952, 4956, 4960, 4964, 4897, 4901, 4905, 4909, 4913, 4917, 4921, 4925, 4929, 4933, 4937, 4941, 4945, 4949, 4953, 4957, 4961, 4965, 4898, 4902, 4906, 4910, 4914, 4918, 4922, 4926, 4930, 4934, 4938, 4942, 4946, 4950, 4954, 4958, 4962, 4966, 4899, 4903, 4907, 4911, 4915, 4919, 4923, 4927, 4931, 4935, 4939, 4943, 4947, 4951, 4955, 4959, 4963, 4967, 5004, 5008, 5012, 5016, 5020, 5024, 5028, 5032, 5036, 5040, 5044, 5048, 5052, 5056, 5060, 5064, 5068, 5072, 5005, 5009, 5013, 5017, 5021, 5025, 5029, 5033, 5037, 5041, 5045, 5049, 5053, 5057, 5061, 5065, 5069, 5073, 5006, 5010, 5014, 5018, 5022, 5026, 5030, 5034, 5038, 5042, 5046, 5050, 5054, 5058, 5062, 5066, 5070, 5074, 5007, 5011, 5015, 5019, 5023, 5027, 5031, 5035, 5039, 5043, 5047, 5051, 5055, 5059, 5063, 5067, 5071, 5075, 5112, 5116, 5120, 5124, 5128, 5132, 5136, 5140, 5144, 5148, 5152, 5156, 5160, 5164, 5168, 5172, 5176, 5180, 5113, 5117, 5121, 5125, 5129, 5133, 5137, 5141, 5145, 5149, 5153, 5157, 5161, 5165, 5169, 5173, 5177, 5181, 5114, 5118, 5122, 5126, 5130, 5134, 5138, 5142, 5146, 5150, 5154, 5158, 5162, 5166, 5170, 5174, 5178, 5182, 5115, 5119, 5123, 5127, 5131, 5135, 5139, 5143, 5147, 5151, 5155, 5159, 5163, 5167, 5171, 5175, 5179, 5183, 5220, 5224, 5228, 5232, 5236, 5240, 5244, 5248, 5252, 5256, 5260, 5264, 5268, 5272, 5276, 5280, 5284, 5288, 5221, 5225, 5229, 5233, 5237, 5241, 5245, 5249, 5253, 5257, 5261, 5265, 5269, 5273, 5277, 5281, 5285, 5289, 5222, 5226, 5230, 5234, 5238, 5242, 5246, 5250, 5254, 5258, 5262, 5266, 5270, 5274, 5278, 5282, 5286, 5290, 5223, 5227, 5231, 5235, 5239, 5243, 5247, 5251, 5255, 5259, 5263, 5267, 5271, 5275, 5279, 5283, 5287, 5291, 5328, 5332, 5336, 5340, 5344, 5348, 5352, 5356, 5360, 5364, 5368, 5372, 5376, 5380, 5384, 5388, 5392, 5396, 5329, 5333, 5337, 5341, 5345, 5349, 5353, 5357, 5361, 5365, 5369, 5373, 5377, 5381, 5385, 5389, 5393, 5397, 5330, 5334, 5338, 5342, 5346, 5350, 5354, 5358, 5362, 5366, 5370, 5374, 5378, 5382, 5386, 5390, 5394, 5398, 5331, 5335, 5339, 5343, 5347, 5351, 5355, 5359, 5363, 5367, 5371, 5375, 5379, 5383, 5387, 5391, 5395, 5399, 5436, 5440, 5444, 5448, 5452, 5456, 5460, 5464, 5468, 5472, 5476, 5480, 5484, 5488, 5492, 5496, 5500, 5504, 5437, 5441, 5445, 5449, 5453, 5457, 5461, 5465, 5469, 5473, 5477, 5481, 5485, 5489, 5493, 5497, 5501, 5505, 5438, 5442, 5446, 5450, 5454, 5458, 5462, 5466, 5470, 5474, 5478, 5482, 5486, 5490, 5494, 5498, 5502, 5506, 5439, 5443, 5447, 5451, 5455, 5459, 5463, 5467, 5471, 5475, 5479, 5483, 5487, 5491, 5495, 5499, 5503, 5507, 5544, 5548, 5552, 5556, 5560, 5564, 5568, 5572, 5576, 5580, 5584, 5588, 5592, 5596, 5600, 5604, 5608, 5612, 5545, 5549, 5553, 5557, 5561, 5565, 5569, 5573, 5577, 5581, 5585, 5589, 5593, 5597, 5601, 5605, 5609, 5613, 5546, 5550, 5554, 5558, 5562, 5566, 5570, 5574, 5578, 5582, 5586, 5590, 5594, 5598, 5602, 5606, 5610, 5614, 5547, 5551, 5555, 5559, 5563, 5567, 5571, 5575, 5579, 5583, 5587, 5591, 5595, 5599, 5603, 5607, 5611, 5615, 5652, 5656, 5660, 5664, 5668, 5672, 5676, 5680, 5684, 5688, 5692, 5696, 5700, 5704, 5708, 5712, 5716, 5720, 5653, 5657, 5661, 5665, 5669, 5673, 5677, 5681, 5685, 5689, 5693, 5697, 5701, 5705, 5709, 5713, 5717, 5721, 5654, 5658, 5662, 5666, 5670, 5674, 5678, 5682, 5686, 5690, 5694, 5698, 5702, 5706, 5710, 5714, 5718, 5722, 5655, 5659, 5663, 5667, 5671, 5675, 5679, 5683, 5687, 5691, 5695, 5699, 5703, 5707, 5711, 5715, 5719, 5723, 5760, 5764, 5768, 5772, 5776, 5780, 5784, 5788, 5792, 5796, 5800, 5804, 5808, 5812, 5816, 5820, 5824, 5828, 5761, 5765, 5769, 5773, 5777, 5781, 5785, 5789, 5793, 5797, 5801, 5805, 5809, 5813, 5817, 5821, 5825, 5829, 5762, 5766, 5770, 5774, 5778, 5782, 5786, 5790, 5794, 5798, 5802, 5806, 5810, 5814, 5818, 5822, 5826, 5830, 5763, 5767, 5771, 5775, 5779, 5783, 5787, 5791, 5795, 5799, 5803, 5807, 5811, 5815, 5819, 5823, 5827, 5831, 5868, 5872, 5876, 5880, 5884, 5888, 5892, 5896, 5900, 5904, 5908, 5912, 5916, 5920, 5924, 5928, 5932, 5936, 5869, 5873, 5877, 5881, 5885, 5889, 5893, 5897, 5901, 5905, 5909, 5913, 5917, 5921, 5925, 5929, 5933, 5937, 5870, 5874, 5878, 5882, 5886, 5890, 5894, 5898, 5902, 5906, 5910, 5914, 5918, 5922, 5926, 5930, 5934, 5938, 5871, 5875, 5879, 5883, 5887, 5891, 5895, 5899, 5903, 5907, 5911, 5915, 5919, 5923, 5927, 5931, 5935, 5939, 5976, 5980, 5984, 5988, 5992, 5996, 6000, 6004, 6008, 6012, 6016, 6020, 6024, 6028, 6032, 6036, 6040, 6044, 5977, 5981, 5985, 5989, 5993, 5997, 6001, 6005, 6009, 6013, 6017, 6021, 6025, 6029, 6033, 6037, 6041, 6045, 5978, 5982, 5986, 5990, 5994, 5998, 6002, 6006, 6010, 6014, 6018, 6022, 6026, 6030, 6034, 6038, 6042, 6046, 5979, 5983, 5987, 5991, 5995, 5999, 6003, 6007, 6011, 6015, 6019, 6023, 6027, 6031, 6035, 6039, 6043, 6047, 6084, 6088, 6092, 6096, 6100, 6104, 6108, 6112, 6116, 6120, 6124, 6128, 6132, 6136, 6140, 6144, 6148, 6152, 6085, 6089, 6093, 6097, 6101, 6105, 6109, 6113, 6117, 6121, 6125, 6129, 6133, 6137, 6141, 6145, 6149, 6153, 6086, 6090, 6094, 6098, 6102, 6106, 6110, 6114, 6118, 6122, 6126, 6130, 6134, 6138, 6142, 6146, 6150, 6154, 6087, 6091, 6095, 6099, 6103, 6107, 6111, 6115, 6119, 6123, 6127, 6131, 6135, 6139, 6143, 6147, 6151, 6155, 6192, 6196, 6200, 6204, 6208, 6212, 6216, 6220, 6224, 6228, 6232, 6236, 6240, 6244, 6248, 6252, 6256, 6260, 6193, 6197, 6201, 6205, 6209, 6213, 6217, 6221, 6225, 6229, 6233, 6237, 6241, 6245, 6249, 6253, 6257, 6261, 6194, 6198, 6202, 6206, 6210, 6214, 6218, 6222, 6226, 6230, 6234, 6238, 6242, 6246, 6250, 6254, 6258, 6262, 6195, 6199, 6203, 6207, 6211, 6215, 6219, 6223, 6227, 6231, 6235, 6239, 6243, 6247, 6251, 6255, 6259, 6263, 6300, 6304, 6308, 6312, 6316, 6320, 6324, 6328, 6332, 6336, 6340, 6344, 6348, 6352, 6356, 6360, 6364, 6368, 6301, 6305, 6309, 6313, 6317, 6321, 6325, 6329, 6333, 6337, 6341, 6345, 6349, 6353, 6357, 6361, 6365, 6369, 6302, 6306, 6310, 6314, 6318, 6322, 6326, 6330, 6334, 6338, 6342, 6346, 6350, 6354, 6358, 6362, 6366, 6370, 6303, 6307, 6311, 6315, 6319, 6323, 6327, 6331, 6335, 6339, 6343, 6347, 6351, 6355, 6359, 6363, 6367, 6371, 6408, 6412, 6416, 6420, 6424, 6428, 6432, 6436, 6440, 6444, 6448, 6452, 6456, 6460, 6464, 6468, 6472, 6476, 6409, 6413, 6417, 6421, 6425, 6429, 6433, 6437, 6441, 6445, 6449, 6453, 6457, 6461, 6465, 6469, 6473, 6477, 6410, 6414, 6418, 6422, 6426, 6430, 6434, 6438, 6442, 6446, 6450, 6454, 6458, 6462, 6466, 6470, 6474, 6478, 6411, 6415, 6419, 6423, 6427, 6431, 6435, 6439, 6443, 6447, 6451, 6455, 6459, 6463, 6467, 6471, 6475, 6479, 6516, 6520, 6524, 6528, 6532, 6536, 6540, 6544, 6548, 6552, 6556, 6560, 6564, 6568, 6572, 6576, 6580, 6584, 6517, 6521, 6525, 6529, 6533, 6537, 6541, 6545, 6549, 6553, 6557, 6561, 6565, 6569, 6573, 6577, 6581, 6585, 6518, 6522, 6526, 6530, 6534, 6538, 6542, 6546, 6550, 6554, 6558, 6562, 6566, 6570, 6574, 6578, 6582, 6586, 6519, 6523, 6527, 6531, 6535, 6539, 6543, 6547, 6551, 6555, 6559, 6563, 6567, 6571, 6575, 6579, 6583, 6587, 6624, 6628, 6632, 6636, 6640, 6644, 6648, 6652, 6656, 6660, 6664, 6668, 6672, 6676, 6680, 6684, 6688, 6692, 6625, 6629, 6633, 6637, 6641, 6645, 6649, 6653, 6657, 6661, 6665, 6669, 6673, 6677, 6681, 6685, 6689, 6693, 6626, 6630, 6634, 6638, 6642, 6646, 6650, 6654, 6658, 6662, 6666, 6670, 6674, 6678, 6682, 6686, 6690, 6694, 6627, 6631, 6635, 6639, 6643, 6647, 6651, 6655, 6659, 6663, 6667, 6671, 6675, 6679, 6683, 6687, 6691, 6695, 6732, 6736, 6740, 6744, 6748, 6752, 6756, 6760, 6764, 6768, 6772, 6776, 6780, 6784, 6788, 6792, 6796, 6800, 6733, 6737, 6741, 6745, 6749, 6753, 6757, 6761, 6765, 6769, 6773, 6777, 6781, 6785, 6789, 6793, 6797, 6801, 6734, 6738, 6742, 6746, 6750, 6754, 6758, 6762, 6766, 6770, 6774, 6778, 6782, 6786, 6790, 6794, 6798, 6802, 6735, 6739, 6743, 6747, 6751, 6755, 6759, 6763, 6767, 6771, 6775, 6779, 6783, 6787, 6791, 6795, 6799, 6803, 6840, 6844, 6848, 6852, 6856, 6860, 6864, 6868, 6872, 6876, 6880, 6884, 6888, 6892, 6896, 6900, 6904, 6908, 6841, 6845, 6849, 6853, 6857, 6861, 6865, 6869, 6873, 6877, 6881, 6885, 6889, 6893, 6897, 6901, 6905, 6909, 6842, 6846, 6850, 6854, 6858, 6862, 6866, 6870, 6874, 6878, 6882, 6886, 6890, 6894, 6898, 6902, 6906, 6910, 6843, 6847, 6851, 6855, 6859, 6863, 6867, 6871, 6875, 6879, 6883, 6887, 6891, 6895, 6899, 6903, 6907, 6911, 6948, 6952, 6956, 6960, 6964, 6968, 6972, 6976, 6980, 6984, 6988, 6992, 6996, 7000, 7004, 7008, 7012, 7016, 6949, 6953, 6957, 6961, 6965, 6969, 6973, 6977, 6981, 6985, 6989, 6993, 6997, 7001, 7005, 7009, 7013, 7017, 6950, 6954, 6958, 6962, 6966, 6970, 6974, 6978, 6982, 6986, 6990, 6994, 6998, 7002, 7006, 7010, 7014, 7018, 6951, 6955, 6959, 6963, 6967, 6971, 6975, 6979, 6983, 6987, 6991, 6995, 6999, 7003, 7007, 7011, 7015, 7019, 7056, 7060, 7064, 7068, 7072, 7076, 7080, 7084, 7088, 7092, 7096, 7100, 7104, 7108, 7112, 7116, 7120, 7124, 7057, 7061, 7065, 7069, 7073, 7077, 7081, 7085, 7089, 7093, 7097, 7101, 7105, 7109, 7113, 7117, 7121, 7125, 7058, 7062, 7066, 7070, 7074, 7078, 7082, 7086, 7090, 7094, 7098, 7102, 7106, 7110, 7114, 7118, 7122, 7126, 7059, 7063, 7067, 7071, 7075, 7079, 7083, 7087, 7091, 7095, 7099, 7103, 7107, 7111, 7115, 7119, 7123, 7127, 7164, 7168, 7172, 7176, 7180, 7184, 7188, 7192, 7196, 7200, 7204, 7208, 7212, 7216, 7220, 7224, 7228, 7232, 7165, 7169, 7173, 7177, 7181, 7185, 7189, 7193, 7197, 7201, 7205, 7209, 7213, 7217, 7221, 7225, 7229, 7233, 7166, 7170, 7174, 7178, 7182, 7186, 7190, 7194, 7198, 7202, 7206, 7210, 7214, 7218, 7222, 7226, 7230, 7234, 7167, 7171, 7175, 7179, 7183, 7187, 7191, 7195, 7199, 7203, 7207, 7211, 7215, 7219, 7223, 7227, 7231, 7235, 7272, 7276, 7280, 7284, 7288, 7292, 7296, 7300, 7304, 7308, 7312, 7316, 7320, 7324, 7328, 7332, 7336, 7340, 7273, 7277, 7281, 7285, 7289, 7293, 7297, 7301, 7305, 7309, 7313, 7317, 7321, 7325, 7329, 7333, 7337, 7341, 7274, 7278, 7282, 7286, 7290, 7294, 7298, 7302, 7306, 7310, 7314, 7318, 7322, 7326, 7330, 7334, 7338, 7342, 7275, 7279, 7283, 7287, 7291, 7295, 7299, 7303, 7307, 7311, 7315, 7319, 7323, 7327, 7331, 7335, 7339, 7343 ],
}, formatters={
	'INIT_VAL': lambda key,val: str(len(val)) + "'h" + "".join([format(bit, '02x') for bit in bits_to_bytes(val[::-1])]),
	'RMUX[0-9][0-9]': lambda key,val: mux_format(val, 7, 'I'),
	'IMUX[0-9][0-9]': lambda key,val: mux_format(val, 9, 'I'),
	'CtrlMUX[0-9][0-9]': lambda key,val: mux_format(val, 8, 'I'),
}, key_transformers={
    'INIT_VAL\[[^\]]*]': lambda x: 'INIT_VAL',
}, encoders={
    'INIT_VAL': lambda key,val: val[::-1],
	'RMUX[0-9][0-9]': lambda key,val: mux_encode(val, 7, 3),
	'IMUX[0-9][0-9]': lambda key,val: mux_encode(val, 9, 3),
	'CtrlMUX[0-9][0-9]': lambda key,val: mux_encode(val, 8, 4),
    # XXX: Haven't verified...
    'BramClkMUX0[0-9]': lambda key, val: mux_encode(val, 3, 1),
    'SeamMUX[0-9][0-9]': lambda key, val: mux_encode(val, 7, 1),
    'TileAsyncMUX0[0-9]': lambda key, val: mux_encode(val, 4, 0),
    'TileClkEnMUX0[0-9]': lambda key, val: mux_encode(val, 3, 0), 
    'TileWeRenMUX0[0-9]': lambda key, val: mux_encode(val, 4, 0),
}, annotations={
	'BramClkMUX00': 'Clk0',
	'BramClkMUX01': 'Clk1',
	'IMUX00': 'AddressA[0]',
	'IMUX01': 'AddressA[1]',
	'IMUX02': 'AddressA[2]',
	'IMUX03': 'AddressA[3]',
	'IMUX04': 'AddressA[4]',
	'IMUX05': 'AddressA[5]',
	'IMUX06': 'AddressA[6]',
	'IMUX07': 'AddressA[7]',
	'IMUX08': 'AddressA[8]',
	'IMUX09': 'AddressA[9]',
	'IMUX10': 'AddressA[10]',
	'IMUX11': 'AddressA[11]',
	'IMUX12': 'DataInA[0]',
	'IMUX13': 'DataInA[1]',
	'IMUX14': 'DataInA[2]',
	'IMUX15': 'DataInA[3]',
	'IMUX16': 'DataInA[4]',
	'IMUX17': 'DataInA[5]',
	'IMUX18': 'DataInA[6]',
	'IMUX19': 'DataInA[7]',
	'IMUX20': 'DataInA[8]',
	'IMUX21': 'DataInA[9]',
	'IMUX22': 'DataInA[10]',
	'IMUX23': 'DataInA[11]',
	'IMUX24': 'DataInA[12]',
	'IMUX25': 'DataInA[13]',
	'IMUX26': 'DataInA[14]',
	'IMUX27': 'DataInA[15]',
	'IMUX28': 'DataInA[16]',
	'IMUX29': 'DataInA[17]',
	'IMUX29': 'DataInA[17]',
	'IMUX34': 'DataInB[17]',
	'IMUX35': 'DataInB[16]',
	'IMUX36': 'DataInB[15]',
	'IMUX37': 'DataInB[14]',
	'IMUX38': 'DataInB[13]',
	'IMUX39': 'DataInB[12]',
	'IMUX40': 'DataInB[11]',
	'IMUX41': 'DataInB[10]',
	'IMUX42': 'DataInB[9]',
	'IMUX43': 'DataInB[8]',
	'IMUX44': 'DataInB[7]',
	'IMUX45': 'DataInB[6]',
	'IMUX46': 'DataInB[5]',
	'IMUX47': 'DataInB[4]',
	'IMUX48': 'DataInB[3]',
	'IMUX49': 'DataInB[2]',
	'IMUX50': 'DataInB[1]',
	'IMUX51': 'DataInB[0]',
	'IMUX52': 'AddressB[11]',
	'IMUX53': 'AddressB[10]',
	'IMUX54': 'AddressB[9]',
	'IMUX55': 'AddressB[8]',
	'IMUX56': 'AddressB[7]',
	'IMUX57': 'AddressB[6]',
	'IMUX58': 'AddressB[5]',
	'IMUX59': 'AddressB[4]',
	'IMUX60': 'AddressB[3]',
	'IMUX61': 'AddressB[2]',
	'IMUX62': 'AddressB[1]',
	'IMUX63': 'AddressB[0]',
	'TileAsyncMUX00':'AsyncReset0',
	'TileAsyncMUX01':'AsyncReset1',
	'TileClkEnMUX00':'ClkEn0',
	'TileClkEnMUX01':'ClkEn1',
	'TileWeRenMUX00':'WeRenA',
	'TileWeRenMUX01':'WeRenB',
}))

InstallTile(Tile('ALTA_PLLX', 'PLLTILE', columns=0, rows=0, slices=0, values={}))

InstallTile(Tile('ALTA_TILE_SRAM_DIST', 'LogicTILE', columns=34, rows=68, slices=16, values={
	# 16 slices per tile

    # Presumably selects between alta_asyncctrl00:Dout/TileAsyncMUX00 
    # and alta_asyncctrl01:Dout/TileAsyncMUX01
	'AsyncMUX00':[32],
	'AsyncMUX01':[168],
	'AsyncMUX02':[304],
	'AsyncMUX03':[440],
	'AsyncMUX04':[576],
	'AsyncMUX05':[712],
	'AsyncMUX06':[848],
	'AsyncMUX07':[984],
	'AsyncMUX08':[1256],
	'AsyncMUX09':[1392],
	'AsyncMUX10':[1528],
	'AsyncMUX11':[1664],
	'AsyncMUX12':[1800],
	'AsyncMUX13':[1936],
	'AsyncMUX14':[2072],
	'AsyncMUX15':[2208],

    # Presumably selects between alta_clkenctrl00:ClkOut/TileClkMUX00 
    # and alta_clkenctrl01:ClkOut/TileClkMUX01
	'ClkMUX00':[66],
	'ClkMUX01':[202],
	'ClkMUX02':[338],
	'ClkMUX03':[474],
	'ClkMUX04':[610],
	'ClkMUX05':[746],
	'ClkMUX06':[882],
	'ClkMUX07':[1018],
	'ClkMUX08':[1290],
	'ClkMUX09':[1426],
	'ClkMUX10':[1562],
	'ClkMUX11':[1698],
	'ClkMUX12':[1834],
	'ClkMUX13':[1970],
	'ClkMUX14':[2106],
	'ClkMUX15':[2242],

    # Feeds TileClkMUX, TileClkEnMUX, TileAsyncMUX, TileSyncMUX
	'CtrlMUX00': [ 1103, 1137, 1104, 1138, 1105, 1139, 1106, 1140, 1107, 1141, 1108, 1142 ],
	'CtrlMUX01': [ 1114, 1148, 1113, 1147, 1112, 1146, 1111, 1145, 1110, 1144, 1109, 1143 ],
	'CtrlMUX02': [ 1205, 1171, 1206, 1172, 1207, 1173, 1208, 1174, 1209, 1175, 1210, 1176 ],
	'CtrlMUX03': [ 1216, 1182, 1215, 1181, 1214, 1180, 1213, 1179, 1212, 1178, 1211, 1177 ],

	# DSTRSTB contains 2 entries of 1 bit each (SLICE_SRAMCTRL)
	'DSTRSTB': [ 1136, 1170 ],

	'RMUX00':[4,38,3,37,2,36,1,0,34,35],
	'RMUX01':[276,310,275,309,274,308,273,272,306,307],
	'RMUX02':[5,39,6,40,7,41,8,9,43,42],
	'RMUX03':[277,311,278,312,279,313,280,281,315,314],
	'RMUX04':[14,48,13,47,12,46,11,10,44,45],
	'RMUX05':[286,320,285,319,284,318,283,282,316,317],
	'RMUX06':[72,106,71,105,70,104,69,68,102,103],
	'RMUX07':[344,378,343,377,342,376,341,340,374,375],
	'RMUX08':[73,107,74,108,75,109,76,77,111,110],
	'RMUX09':[345,379,346,380,347,381,348,349,383,382],
	'RMUX10':[82,116,81,115,80,114,79,78,112,113],
	'RMUX11':[354,388,353,387,352,386,351,350,384,385],
	'RMUX12':[413,447,414,448,415,449,416,417,451,450],
	'RMUX13':[141,175,142,176,143,177,144,145,179,178],
	'RMUX14':[422,456,421,455,420,454,419,418,452,453],
	'RMUX15':[150,184,149,183,148,182,147,146,180,181],
	'RMUX16':[412,446,411,445,410,444,409,408,442,443],
	'RMUX17':[140,174,139,173,138,172,137,136,170,171],
	'RMUX18':[481,515,482,516,483,517,484,485,519,518],
	'RMUX19':[209,243,210,244,211,245,212,213,247,246],
	'RMUX20':[490,524,489,523,488,522,487,486,520,521],
	'RMUX21':[218,252,217,251,216,250,215,214,248,249],
	'RMUX22':[480,514,479,513,478,512,477,476,510,511],
	'RMUX23':[208,242,207,241,206,240,205,204,238,239],
	'RMUX24':[548,582,547,581,546,580,545,544,578,579],
	'RMUX25':[820,854,819,853,818,852,817,816,850,851],
	'RMUX26':[549,583,550,584,551,585,552,553,587,586],
	'RMUX27':[821,855,822,856,823,857,824,825,859,858],
	'RMUX28':[558,592,557,591,556,590,555,554,588,589],
	'RMUX29':[830,864,829,863,828,862,827,826,860,861],
	'RMUX30':[616,650,615,649,614,648,613,612,646,647],
	'RMUX31':[888,922,887,921,886,920,885,884,918,919],
	'RMUX32':[617,651,618,652,619,653,620,621,655,654],
	'RMUX33':[889,923,890,924,891,925,892,893,927,926],
	'RMUX34':[626,660,625,659,624,658,623,622,656,657],
	'RMUX35':[898,932,897,931,896,930,895,894,928,929],
	'RMUX36':[957,991,958,992,959,993,960,961,995,994],
	'RMUX37':[685,719,686,720,687,721,688,689,723,722],
	'RMUX38':[966,1000,965,999,964,998,963,962,996,997],
	'RMUX39':[694,728,693,727,692,726,691,690,724,725],
	'RMUX40':[956,990,955,989,954,988,953,952,986,987],
	'RMUX41':[684,718,683,717,682,716,681,680,714,715],
	'RMUX42':[1025,1059,1026,1060,1027,1061,1028,1029,1063,1062],
	'RMUX43':[753,787,754,788,755,789,756,757,791,790],
	'RMUX44':[1034,1068,1033,1067,1032,1066,1031,1030,1064,1065],
	'RMUX45':[762,796,761,795,760,794,759,758,792,793],
	'RMUX46':[1024,1058,1023,1057,1022,1056,1021,1020,1054,1055],
	'RMUX47':[752,786,751,785,750,784,749,748,782,783],
	'RMUX48':[1228,1262,1227,1261,1226,1260,1225,1224,1258,1259],
	'RMUX49':[1500,1534,1499,1533,1498,1532,1497,1496,1530,1531],
	'RMUX50':[1229,1263,1230,1264,1231,1265,1232,1233,1267,1266],
	'RMUX51':[1501,1535,1502,1536,1503,1537,1504,1505,1539,1538],
	'RMUX52':[1238,1272,1237,1271,1236,1270,1235,1234,1268,1269],
	'RMUX53':[1510,1544,1509,1543,1508,1542,1507,1506,1540,1541],
	'RMUX54':[1296,1330,1295,1329,1294,1328,1293,1292,1326,1327],
	'RMUX55':[1568,1602,1567,1601,1566,1600,1565,1564,1598,1599],
	'RMUX56':[1297,1331,1298,1332,1299,1333,1300,1301,1335,1334],
	'RMUX57':[1569,1603,1570,1604,1571,1605,1572,1573,1607,1606],
	'RMUX58':[1306,1340,1305,1339,1304,1338,1303,1302,1336,1337],
	'RMUX59':[1578,1612,1577,1611,1576,1610,1575,1574,1608,1609],
	'RMUX60':[1637,1671,1638,1672,1639,1673,1640,1641,1675,1674],
	'RMUX61':[1365,1399,1366,1400,1367,1401,1368,1369,1403,1402],
	'RMUX62':[1646,1680,1645,1679,1644,1678,1643,1642,1676,1677],
	'RMUX63':[1374,1408,1373,1407,1372,1406,1371,1370,1404,1405],
	'RMUX64':[1636,1670,1635,1669,1634,1668,1633,1632,1666,1667],
	'RMUX65':[1364,1398,1363,1397,1362,1396,1361,1360,1394,1395],
	'RMUX66':[1705,1739,1706,1740,1707,1741,1708,1709,1743,1742],
	'RMUX67':[1433,1467,1434,1468,1435,1469,1436,1437,1471,1470],
	'RMUX68':[1714,1748,1713,1747,1712,1746,1711,1710,1744,1745],
	'RMUX69':[1442,1476,1441,1475,1440,1474,1439,1438,1472,1473],
	'RMUX70':[1704,1738,1703,1737,1702,1736,1701,1700,1734,1735],
	'RMUX71':[1432,1466,1431,1465,1430,1464,1429,1428,1462,1463],
	'RMUX72':[1772,1806,1771,1805,1770,1804,1769,1768,1802,1803],
	'RMUX73':[2044,2078,2043,2077,2042,2076,2041,2040,2074,2075],
	'RMUX74':[1773,1807,1774,1808,1775,1809,1776,1777,1811,1810],
	'RMUX75':[2045,2079,2046,2080,2047,2081,2048,2049,2083,2082],
	'RMUX76':[1782,1816,1781,1815,1780,1814,1779,1778,1812,1813],
	'RMUX77':[2054,2088,2053,2087,2052,2086,2051,2050,2084,2085],
	'RMUX78':[1840,1874,1839,1873,1838,1872,1837,1836,1870,1871],
	'RMUX79':[2112,2146,2111,2145,2110,2144,2109,2108,2142,2143],
	'RMUX80':[1841,1875,1842,1876,1843,1877,1844,1845,1879,1878],
	'RMUX81':[2113,2147,2114,2148,2115,2149,2116,2117,2151,2150],
	'RMUX82':[1850,1884,1849,1883,1848,1882,1847,1846,1880,1881],
	'RMUX83':[2122,2156,2121,2155,2120,2154,2119,2118,2152,2153],
	'RMUX84':[2181,2215,2182,2216,2183,2217,2184,2185,2219,2218],
	'RMUX85':[1909,1943,1910,1944,1911,1945,1912,1913,1947,1946],
	'RMUX86':[2190,2224,2189,2223,2188,2222,2187,2186,2220,2221],
	'RMUX87':[1918,1952,1917,1951,1916,1950,1915,1914,1948,1949],
	'RMUX88':[2180,2214,2179,2213,2178,2212,2177,2176,2210,2211],
	'RMUX89':[1908,1942,1907,1941,1906,1940,1905,1904,1938,1939],
	'RMUX90':[2249,2283,2250,2284,2251,2285,2252,2253,2287,2286],
	'RMUX91':[1977,2011,1978,2012,1979,2013,1980,1981,2015,2014],
	'RMUX92':[2258,2292,2257,2291,2256,2290,2255,2254,2288,2289],
	'RMUX93':[1986,2020,1985,2019,1984,2018,1983,1982,2016,2017],
	'RMUX94':[2248,2282,2247,2281,2246,2280,2245,2244,2278,2279],
	'RMUX95':[1976,2010,1975,2009,1974,2008,1973,1972,2006,2007],

	'SeamMUX00':[1088,1089,1090,1091,1092,1093,1094,1095],
	'SeamMUX01':[1190,1191,1192,1193,1194,1195,1196,1197],
	'SeamMUX02':[1096,1097,1135,1098,1099,1100,1101,1102],
	'SeamMUX03':[1198,1199,1169,1200,1201,1202,1203,1204],

	'TileAsyncMUX00':[1152,1151,1150,1149],
	'TileAsyncMUX01':[1186,1185,1184,1183],

	'TileClkEnMUX00':[1223,1222,1221],
	'TileClkEnMUX01':[1121,1120,1119],

    # 0100 = CtrlMUX00, 0010 = CtrlMUX01
	'TileClkMUX00':[1118,1117,1116,1115],
    # 0100 = CtrlMUX02, 0010 = CtrlMUX03
	'TileClkMUX01':[1220,1219,1218,1217],

	'TileSyncMUX00':[1189,1188,1187],
	'TileSyncMUX01':[1155,1154,1153],


	# LUTs appear reversed and inverted from their counterparts in the _routed.v file.
	# e.g. defparam syn__49_.mask = 16'h78F0 (0111 1000 1111 0000)
	# this tool prints out
	# alta_slice08_LUT: 1111 0000 1110 0001 (F0E1)
	# Those bits reversed:
	# 1000 0111 0000 1111
	# and inverted:
	# 0111 1000 1111 0000
	'alta_slice00_BYPASSEN':[134],
	'alta_slice00_CARRY_CRL':[99],
	'alta_slice00_LUTCMUX':[133,31],
	'alta_slice00_LUT':[30,27,29,28,63,62,64,61,98,95,97,96,131,130,132,129],
	'alta_slice00_SHIFTMUX':[100],
	'alta_slice00_IMUX00':[15,49,16,50,17,51,18,52,19,20,54,53],	   	# A
	'alta_slice00_IMUX01':[26,60,25,59,24,58,23,57,22,21,55,56],			# B
	'alta_slice00_IMUX02':[83,117,84,118,85,119,86,120,87,88,122,121],	# C
	'alta_slice00_IMUX03':[94,128,93,127,92,126,91,125,90,89,123,124],	# D
	'alta_slice00_OMUX00':[33],
	'alta_slice00_OMUX01':[101],
	'alta_slice00_OMUX02':[135],

	'alta_slice01_BYPASSEN':[270],
	'alta_slice01_CARRY_CRL':[235],
	'alta_slice01_LUTCMUX':[269,167],
	'alta_slice01_LUT':[166,163,165,164,199,198,200,197,234,231,233,232,267,266,268,265],
	'alta_slice01_SHIFTMUX':[236],
	'alta_slice01_IMUX04':[151,185,152,186,153,187,154,188,155,156,190,189],	# A
	'alta_slice01_IMUX05':[162,196,161,195,160,194,159,193,158,157,191,192],	# B
	'alta_slice01_IMUX06':[219,253,220,254,221,255,222,256,223,224,258,257],	# C
	'alta_slice01_IMUX07':[230,264,229,263,228,262,227,261,226,225,259,260],	# D
	'alta_slice01_OMUX03':[169],
	'alta_slice01_OMUX04':[237],
	'alta_slice01_OMUX05':[271],

	'alta_slice02_BYPASSEN':[406],
	'alta_slice02_CARRY_CRL':[371],
	'alta_slice02_LUTCMUX':[405,303],
	'alta_slice02_LUT':[302,299,301,300,335,334,336,333,370,367,369,368,403,402,404,401],
	'alta_slice02_SHIFTMUX':[372],
	'alta_slice02_IMUX08':[287,321,288,322,289,323,290,324,291,292,326,325],	# A
	'alta_slice02_IMUX09':[298,332,297,331,296,330,295,329,294,293,327,328],	# B
	'alta_slice02_IMUX10':[355,389,356,390,357,391,358,392,359,360,394,393],	# C
	'alta_slice02_IMUX11':[366,400,365,399,364,398,363,397,362,361,395,396],	# D
	'alta_slice02_OMUX06':[305],
	'alta_slice02_OMUX07':[373],
	'alta_slice02_OMUX08':[407],

	'alta_slice03_BYPASSEN':[542],
	'alta_slice03_CARRY_CRL':[507],
	'alta_slice03_LUTCMUX':[541,439],
	'alta_slice03_LUT':[438,435,437,436,471,470,472,469,506,503,505,504,539,538,540,537],
	'alta_slice03_SHIFTMUX':[508],
	'alta_slice03_IMUX12':[423,457,424,458,425,459,426,460,427,428,462,461],	# A
	'alta_slice03_IMUX13':[434,468,433,467,432,466,431,465,430,429,463,464],	# B
	'alta_slice03_IMUX14':[491,525,492,526,493,527,494,528,495,496,530,529],	# C
	'alta_slice03_IMUX15':[502,536,501,535,500,534,499,533,498,497,531,532],	# D
	'alta_slice03_OMUX09':[441],
	'alta_slice03_OMUX10':[509],
	'alta_slice03_OMUX11':[543],

	'alta_slice04_BYPASSEN':[678],
	'alta_slice04_CARRY_CRL':[643],
	'alta_slice04_LUTCMUX':[677,575],
	'alta_slice04_LUT':[574,571,573,572,607,606,608,605,642,639,641,640,675,674,676,673],
	'alta_slice04_SHIFTMUX':[644],
	'alta_slice04_IMUX16':[559,593,560,594,561,595,562,596,563,564,598,597],	# A
	'alta_slice04_IMUX17':[570,604,569,603,568,602,567,601,566,565,599,600],	# B
	'alta_slice04_IMUX18':[627,661,628,662,629,663,630,664,631,632,666,665],	# C
	'alta_slice04_IMUX19':[638,672,637,671,636,670,635,669,634,633,667,668],	# D
	'alta_slice04_OMUX12':[577],
	'alta_slice04_OMUX13':[645],
	'alta_slice04_OMUX14':[679],

	'alta_slice05_BYPASSEN':[814],
	'alta_slice05_CARRY_CRL':[779],
	'alta_slice05_LUTCMUX':[813,711],
	'alta_slice05_LUT':[710,707,709,708,743,742,744,741,778,775,777,776,811,810,812,809],
	'alta_slice05_SHIFTMUX':[780],
	'alta_slice05_IMUX20':[695,729,696,730,697,731,698,732,699,700,734,733],	# A
	'alta_slice05_IMUX21':[706,740,705,739,704,738,703,737,702,701,735,736],	# B
	'alta_slice05_IMUX22':[763,797,764,798,765,799,766,800,767,768,802,801],	# C
	'alta_slice05_IMUX23':[774,808,773,807,772,806,771,805,770,769,803,804],	# D
	'alta_slice05_OMUX15':[713],
	'alta_slice05_OMUX16':[781],
	'alta_slice05_OMUX17':[815],

	'alta_slice06_BYPASSEN':[950],
	'alta_slice06_CARRY_CRL':[915],
	'alta_slice06_LUTCMUX':[949,847],
	'alta_slice06_LUT':[846,843,845,844,879,878,880,877,914,911,913,912,947,946,948,945],
	'alta_slice06_SHIFTMUX':[916],
	'alta_slice06_IMUX24':[831,865,832,866,833,867,834,868,835,836,870,869],	# A
	'alta_slice06_IMUX25':[842,876,841,875,840,874,839,873,838,837,871,872],	# B
	'alta_slice06_IMUX26':[899,933,900,934,901,935,902,936,903,904,938,937],	# C
	'alta_slice06_IMUX27':[910,944,909,943,908,942,907,941,906,905,939,940],	# D
	'alta_slice06_OMUX18':[849],
	'alta_slice06_OMUX19':[917],
	'alta_slice06_OMUX20':[951],

	'alta_slice07_BYPASSEN':[1086],
	'alta_slice07_CARRY_CRL':[1051],
	'alta_slice07_LUTCMUX':[1085,983],
	'alta_slice07_LUT':[982,979,981,980,1015,1014,1016,1013,1050,1047,1049,1048,1083,1082,1084,1081],
	'alta_slice07_SHIFTMUX':[1052],
	'alta_slice07_IMUX28':[967,1001,968,1002,969,1003,970,1004,971,972,1006,1005],	# A
	'alta_slice07_IMUX29':[978,1012,977,1011,976,1010,975,1009,974,973,1007,1008],	# B
	'alta_slice07_IMUX30':[1035,1069,1036,1070,1037,1071,1038,1072,1039,1040,1074,1073],	# C
	'alta_slice07_IMUX31':[1046,1080,1045,1079,1044,1078,1043,1077,1042,1041,1075,1076],	# D
	'alta_slice07_OMUX21':[985],
	'alta_slice07_OMUX22':[1053],
	'alta_slice07_OMUX23':[1087],

	'alta_slice08_BYPASSEN':[1358],
	'alta_slice08_CARRY_CRL':[1323],
	'alta_slice08_LUTCMUX':[1357,1255],
	'alta_slice08_LUT':[1254,1251,1253,1252,1287,1286,1288,1285,1322,1319,1321,1320,1355,1354,1356,1353],
	'alta_slice08_SHIFTMUX':[1324],
	'alta_slice08_IMUX32':[1239,1273,1240,1274,1241,1275,1242,1276,1243,1244,1278,1277],	# A
	'alta_slice08_IMUX33':[1250,1284,1249,1283,1248,1282,1247,1281,1246,1245,1279,1280],	# B
	'alta_slice08_IMUX34':[1307,1341,1308,1342,1309,1343,1310,1344,1311,1312,1346,1345],	# C
	'alta_slice08_IMUX35':[1318,1352,1317,1351,1316,1350,1315,1349,1314,1313,1347,1348],	# D
	'alta_slice08_OMUX24':[1257],
	'alta_slice08_OMUX25':[1325],
	'alta_slice08_OMUX26':[1359],

	'alta_slice09_BYPASSEN':[1494],
	'alta_slice09_CARRY_CRL':[1459],
	'alta_slice09_LUTCMUX':[1493,1391],
	'alta_slice09_LUT':[1390,1387,1389,1388,1423,1422,1424,1421,1458,1455,1457,1456,1491,1490,1492,1489],
	'alta_slice09_SHIFTMUX':[1460],
	'alta_slice09_IMUX36':[1375,1409,1376,1410,1377,1411,1378,1412,1379,1380,1414,1413],	# A
	'alta_slice09_IMUX37':[1386,1420,1385,1419,1384,1418,1383,1417,1382,1381,1415,1416],	# B
	'alta_slice09_IMUX38':[1443,1477,1444,1478,1445,1479,1446,1480,1447,1448,1482,1481],	# C
	'alta_slice09_IMUX39':[1454,1488,1453,1487,1452,1486,1451,1485,1450,1449,1483,1484],	# D
	'alta_slice09_OMUX27':[1393],
	'alta_slice09_OMUX28':[1461],
	'alta_slice09_OMUX29':[1495],

	'alta_slice10_BYPASSEN':[1630],
	'alta_slice10_CARRY_CRL':[1595],
	'alta_slice10_LUTCMUX':[1629,1527],
	'alta_slice10_LUT':[1526,1523,1525,1524,1559,1558,1560,1557,1594,1591,1593,1592,1627,1626,1628,1625],
	'alta_slice10_SHIFTMUX':[1596],
	'alta_slice10_IMUX40':[1511,1545,1512,1546,1513,1547,1514,1548,1515,1516,1550,1549],	# A
	'alta_slice10_IMUX41':[1522,1556,1521,1555,1520,1554,1519,1553,1518,1517,1551,1552],	# B
	'alta_slice10_IMUX42':[1579,1613,1580,1614,1581,1615,1582,1616,1583,1584,1618,1617],	# C
	'alta_slice10_IMUX43':[1590,1624,1589,1623,1588,1622,1587,1621,1586,1585,1619,1620],	# D
	'alta_slice10_OMUX30':[1529],
	'alta_slice10_OMUX31':[1597],
	'alta_slice10_OMUX32':[1631],

	'alta_slice11_BYPASSEN':[1766],
	'alta_slice11_CARRY_CRL':[1731],
	'alta_slice11_LUTCMUX':[1765,1663],
	'alta_slice11_LUT':[1662,1659,1661,1660,1695,1694,1696,1693,1730,1727,1729,1728,1763,1762,1764,1761],
	'alta_slice11_SHIFTMUX':[1732],
	'alta_slice11_IMUX44':[1647,1681,1648,1682,1649,1683,1650,1684,1651,1652,1686,1685],	# A
	'alta_slice11_IMUX45':[1658,1692,1657,1691,1656,1690,1655,1689,1654,1653,1687,1688],	# B
	'alta_slice11_IMUX46':[1715,1749,1716,1750,1717,1751,1718,1752,1719,1720,1754,1753],	# C
	'alta_slice11_IMUX47':[1726,1760,1725,1759,1724,1758,1723,1757,1722,1721,1755,1756],	# D
	'alta_slice11_OMUX33':[1665],
	'alta_slice11_OMUX34':[1733],
	'alta_slice11_OMUX35':[1767],

	'alta_slice12_BYPASSEN':[1902],
	'alta_slice12_CARRY_CRL':[1867],
	'alta_slice12_LUTCMUX':[1901,1799],
	'alta_slice12_LUT':[1798,1795,1797,1796,1831,1830,1832,1829,1866,1863,1865,1864,1899,1898,1900,1897],
	'alta_slice12_SHIFTMUX':[1868],
	'alta_slice12_IMUX48':[1783,1817,1784,1818,1785,1819,1786,1820,1787,1788,1822,1821],	# A
	'alta_slice12_IMUX49':[1794,1828,1793,1827,1792,1826,1791,1825,1790,1789,1823,1824],	# B
	'alta_slice12_IMUX50':[1851,1885,1852,1886,1853,1887,1854,1888,1855,1856,1890,1889],	# C
	'alta_slice12_IMUX51':[1862,1896,1861,1895,1860,1894,1859,1893,1858,1857,1891,1892],	# D
	'alta_slice12_OMUX36':[1801],
	'alta_slice12_OMUX37':[1869],
	'alta_slice12_OMUX38':[1903],

	'alta_slice13_BYPASSEN':[2038],
	'alta_slice13_CARRY_CRL':[2003],
	'alta_slice13_LUTCMUX':[2037,1935],
	'alta_slice13_LUT':[1934,1931,1933,1932,1967,1966,1968,1965,2002,1999,2001,2000,2035,2034,2036,2033],
	'alta_slice13_SHIFTMUX':[2004],
	'alta_slice13_IMUX52':[1919,1953,1920,1954,1921,1955,1922,1956,1923,1924,1958,1957],	# A
	'alta_slice13_IMUX53':[1930,1964,1929,1963,1928,1962,1927,1961,1926,1925,1959,1960],	# B
	'alta_slice13_IMUX54':[1987,2021,1988,2022,1989,2023,1990,2024,1991,1992,2026,2025],	# C
	'alta_slice13_IMUX55':[1998,2032,1997,2031,1996,2030,1995,2029,1994,1993,2027,2028],	# D
	'alta_slice13_OMUX39':[1937],
	'alta_slice13_OMUX40':[2005],
	'alta_slice13_OMUX41':[2039],

	'alta_slice14_BYPASSEN':[2174],
	'alta_slice14_CARRY_CRL':[2139],
	'alta_slice14_LUTCMUX':[2173,2071],
	'alta_slice14_LUT':[2070,2067,2069,2068,2103,2102,2104,2101,2138,2135,2137,2136,2171,2170,2172,2169],
	'alta_slice14_SHIFTMUX':[2140],
	'alta_slice14_IMUX56':[2055,2089,2056,2090,2057,2091,2058,2092,2059,2060,2094,2093],	# A
	'alta_slice14_IMUX57':[2066,2100,2065,2099,2064,2098,2063,2097,2062,2061,2095,2096],	# B
	'alta_slice14_IMUX58':[2123,2157,2124,2158,2125,2159,2126,2160,2127,2128,2162,2161],	# C
	'alta_slice14_IMUX59':[2134,2168,2133,2167,2132,2166,2131,2165,2130,2129,2163,2164],	# D
	'alta_slice14_OMUX42':[2073],
	'alta_slice14_OMUX43':[2141],
	'alta_slice14_OMUX44':[2175],

	'alta_slice15_BYPASSEN':[2310],
	'alta_slice15_CARRY_CRL':[2275],
	'alta_slice15_LUTCMUX':[2309,2207],
	'alta_slice15_LUT':[2206,2203,2205,2204,2239,2238,2240,2237,2274,2271,2273,2272,2307,2306,2308,2305],
	'alta_slice15_SHIFTMUX':[2276],
	'alta_slice15_IMUX60':[2191,2225,2192,2226,2193,2227,2194,2228,2195,2196,2230,2229],	# A
	'alta_slice15_IMUX61':[2202,2236,2201,2235,2200,2234,2199,2233,2198,2197,2231,2232],	# B
	'alta_slice15_IMUX62':[2259,2293,2260,2294,2261,2295,2262,2296,2263,2264,2298,2297],	# C
	'alta_slice15_IMUX63':[2270,2304,2269,2303,2268,2302,2267,2301,2266,2265,2299,2300],	# D
	'alta_slice15_OMUX45':[2209],
	'alta_slice15_OMUX46':[2277],
	'alta_slice15_OMUX47':[2311],
}, formatters={
	'^alta_slice[0-9][0-9]_LUT$': lambda key,val: '16\'h'+format(bytes_to_num(bits_to_bytes(lut_decode(key,val))), '04x'),
	'alta_slice[0-9][0-9]_IMUX[0-9][0-9]': lambda key,val: mux_format(val, 9, 'I'),
	'alta_slice[0-9][0-9]_OMUX[0-9][0-9]': lambda key,val: slice_omux_format(val), 
	'RMUX[0-9][0-9]': lambda key,val: mux_format(val, 7, 'I'),
	'CtrlMUX[0-9][0-9]': lambda key,val: mux_format(val, 8, 'I'),
	'TileAsyncMUX0[01]': lambda key,val: bits_to_string(val, 4, True),
	'TileClkEnMUX0[01]': lambda key,val: bits_to_string(val, 3, True),
	'TileClkMUX0[01]': lambda key,val: bits_to_string(val, 4, True),
	'TileSyncMUX0[01]': lambda key,val: bits_to_string(val, 3, True),
}, key_transformers={
    'IMUX[0-9][0-9]': lambda x: "alta_slice%02i_%s" % (int(int(x[4:]) / 4), x),
    'OMUX[0-9][0-9]': lambda x: "alta_slice%02i_%s" % (int(int(x[4:]) / 3), x),
    'alta_slice[0-9][0-9].FF_USED': lambda x: "alta_slice%02i_CARRY_CRL" % (int(x[10:12])),
    'alta_slice[0-9][0-9].INIT': lambda x: re.sub('(alta_slice[0-9][0-9]).INIT', lambda x: x.groups()[0] + "_LUT", x),
}, encoders={
    'alta_slice[0-9][0-9]_IMUX[0-9][0-9]': lambda key,val: mux_encode(val, 9, 3),
    'alta_slice[0-9][0-9]_LUT$': lambda key,val: lut_encode(key,val),
    'alta_slice[0-9][0-9]_LUTCMUX': lambda key,val: [val[0], 0],
    'RMUX[0-9][0-9]': lambda key,val: mux_encode(val, 7, 3),
    'CtrlMUX[0-9][0-9]': lambda key,val: mux_encode(val, 8, 4),
	'TileClkMUX[0-9][0-9]': lambda key,val: mux_encode(val, 4, 0),
	'SeamMUX[0-9][0-9]': lambda key,val: mux_encode(val, 7, 1),
}, annotations={
    'alta_slice[0-9][0-9]_LUTCMUX': 'FeedbackMux?',
	'alta_slice00_IMUX00':'A',
	'alta_slice00_IMUX01':'B',
	'alta_slice00_IMUX02':'C',
	'alta_slice00_IMUX03':'D',
	'alta_slice01_IMUX04':'A',
	'alta_slice01_IMUX05':'B',
	'alta_slice01_IMUX06':'C',
	'alta_slice01_IMUX07':'D',
	'alta_slice02_IMUX08':'A',
	'alta_slice02_IMUX09':'B',
	'alta_slice02_IMUX10':'C',
	'alta_slice02_IMUX11':'D',
	'alta_slice03_IMUX12':'A',
	'alta_slice03_IMUX13':'B',
	'alta_slice03_IMUX14':'C',
	'alta_slice03_IMUX15':'D',
	'alta_slice04_IMUX16':'A',
	'alta_slice04_IMUX17':'B',
	'alta_slice04_IMUX18':'C',
	'alta_slice04_IMUX19':'D',
	'alta_slice05_IMUX20':'A',
	'alta_slice05_IMUX21':'B',
	'alta_slice05_IMUX22':'C',
	'alta_slice05_IMUX23':'D',
	'alta_slice06_IMUX24':'A',
	'alta_slice06_IMUX25':'B',
	'alta_slice06_IMUX26':'C',
	'alta_slice06_IMUX27':'D',
	'alta_slice07_IMUX28':'A',
	'alta_slice07_IMUX29':'B',
	'alta_slice07_IMUX30':'C',
	'alta_slice07_IMUX31':'D',
	'alta_slice08_IMUX32':'A',
	'alta_slice08_IMUX33':'B',
	'alta_slice08_IMUX34':'C',
	'alta_slice08_IMUX35':'D',
	'alta_slice09_IMUX36':'A',
	'alta_slice09_IMUX37':'B',
	'alta_slice09_IMUX38':'C',
	'alta_slice09_IMUX39':'D',
	'alta_slice10_IMUX40':'A',
	'alta_slice10_IMUX41':'B',
	'alta_slice10_IMUX42':'C',
	'alta_slice10_IMUX43':'D',
	'alta_slice11_IMUX44':'A',
	'alta_slice11_IMUX45':'B',
	'alta_slice11_IMUX46':'C',
	'alta_slice11_IMUX47':'D',
	'alta_slice12_IMUX48':'A',
	'alta_slice12_IMUX49':'B',
	'alta_slice12_IMUX50':'C',
	'alta_slice12_IMUX51':'D',
	'alta_slice13_IMUX52':'A',
	'alta_slice13_IMUX53':'B',
	'alta_slice13_IMUX54':'C',
	'alta_slice13_IMUX55':'D',
	'alta_slice14_IMUX56':'A',
	'alta_slice14_IMUX57':'B',
	'alta_slice14_IMUX58':'C',
	'alta_slice14_IMUX59':'D',
	'alta_slice15_IMUX60':'A',
	'alta_slice15_IMUX61':'B',
	'alta_slice15_IMUX62':'C',
	'alta_slice15_IMUX63':'D',
}))

InstallTile(Tile('IOTILE_ROUTE', 'RogicTILE', columns=16, rows=68, slices=0, values={
	'OMUX00': [ 15 ],
	'OMUX01': [ 79 ],
	'OMUX02': [ 143 ],
	'OMUX03': [ 207 ],
	'OMUX04': [ 271 ],
	'OMUX05': [ 335 ],
	'OMUX06': [ 399 ],
	'OMUX07': [ 463 ],
	'OMUX08': [ 591 ],
	'OMUX09': [ 655 ],
	'OMUX10': [ 719 ],
	'OMUX11': [ 783 ],
	'OMUX12': [ 847 ],
	'OMUX13': [ 911 ],
	'OMUX14': [ 975 ],
	'OMUX15': [ 1039 ],

	'RMUX00':[4,20,3,19,2,18,1,0,16,17],
	'RMUX01':[132,148,131,147,130,146,129,128,144,145],
	'RMUX02':[5,21,6,22,7,23,8,9,25,24],
	'RMUX03':[133,149,134,150,135,151,136,137,153,152],
	'RMUX04':[14,30,13,29,12,28,11,10,26,27],
	'RMUX05':[142,158,141,157,140,156,139,138,154,155],
	'RMUX06':[36,52,35,51,34,50,33,32,48,49],
	'RMUX07':[164,180,163,179,162,178,161,160,176,177],
	'RMUX08':[37,53,38,54,39,55,40,41,57,56],
	'RMUX09':[165,181,166,182,167,183,168,169,185,184],
	'RMUX10':[46,62,45,61,44,60,43,42,58,59],
	'RMUX11':[174,190,173,189,172,188,171,170,186,187],
	'RMUX12':[197,213,198,214,199,215,200,201,217,216],
	'RMUX13':[69,85,70,86,71,87,72,73,89,88],
	'RMUX14':[206,222,205,221,204,220,203,202,218,219],
	'RMUX15':[78,94,77,93,76,92,75,74,90,91],
	'RMUX16':[196,212,195,211,194,210,193,192,208,209],
	'RMUX17':[68,84,67,83,66,82,65,64,80,81],
	'RMUX18':[229,245,230,246,231,247,232,233,249,248],
	'RMUX19':[101,117,102,118,103,119,104,105,121,120],
	'RMUX20':[238,254,237,253,236,252,235,234,250,251],
	'RMUX21':[110,126,109,125,108,124,107,106,122,123],
	'RMUX22':[228,244,227,243,226,242,225,224,240,241],
	'RMUX23':[100,116,99,115,98,114,97,96,112,113],
	'RMUX24':[260,276,259,275,258,274,257,256,272,273],
	'RMUX25':[388,404,387,403,386,402,385,384,400,401],
	'RMUX26':[261,277,262,278,263,279,264,265,281,280],
	'RMUX27':[389,405,390,406,391,407,392,393,409,408],
	'RMUX28':[270,286,269,285,268,284,267,266,282,283],
	'RMUX29':[398,414,397,413,396,412,395,394,410,411],
	'RMUX30':[292,308,291,307,290,306,289,288,304,305],
	'RMUX31':[420,436,419,435,418,434,417,416,432,433],
	'RMUX32':[293,309,294,310,295,311,296,297,313,312],
	'RMUX33':[421,437,422,438,423,439,424,425,441,440],
	'RMUX34':[302,318,301,317,300,316,299,298,314,315],
	'RMUX35':[430,446,429,445,428,444,427,426,442,443],
	'RMUX36':[453,469,454,470,455,471,456,457,473,472],
	'RMUX37':[325,341,326,342,327,343,328,329,345,344],
	'RMUX38':[462,478,461,477,460,476,459,458,474,475],
	'RMUX39':[334,350,333,349,332,348,331,330,346,347],
	'RMUX40':[452,468,451,467,450,466,449,448,464,465],
	'RMUX41':[324,340,323,339,322,338,321,320,336,337],
	'RMUX42':[485,501,486,502,487,503,488,489,505,504],
	'RMUX43':[357,373,358,374,359,375,360,361,377,376],
	'RMUX44':[494,510,493,509,492,508,491,490,506,507],
	'RMUX45':[366,382,365,381,364,380,363,362,378,379],
	'RMUX46':[484,500,483,499,482,498,481,480,496,497],
	'RMUX47':[356,372,355,371,354,370,353,352,368,369],
	'RMUX48':[580,596,579,595,578,594,577,576,592,593],
	'RMUX49':[708,724,707,723,706,722,705,704,720,721],
	'RMUX50':[581,597,582,598,583,599,584,585,601,600],
	'RMUX51':[709,725,710,726,711,727,712,713,729,728],
	'RMUX52':[590,606,589,605,588,604,587,586,602,603],
	'RMUX53':[718,734,717,733,716,732,715,714,730,731],
	'RMUX54':[612,628,611,627,610,626,609,608,624,625],
	'RMUX55':[740,756,739,755,738,754,737,736,752,753],
	'RMUX56':[613,629,614,630,615,631,616,617,633,632],
	'RMUX57':[741,757,742,758,743,759,744,745,761,760],
	'RMUX58':[622,638,621,637,620,636,619,618,634,635],
	'RMUX59':[750,766,749,765,748,764,747,746,762,763],
	'RMUX60':[773,789,774,790,775,791,776,777,793,792],
	'RMUX61':[645,661,646,662,647,663,648,649,665,664],
	'RMUX62':[782,798,781,797,780,796,779,778,794,795],
	'RMUX63':[654,670,653,669,652,668,651,650,666,667],
	'RMUX64':[772,788,771,787,770,786,769,768,784,785],
	'RMUX65':[644,660,643,659,642,658,641,640,656,657],
	'RMUX66':[805,821,806,822,807,823,808,809,825,824],
	'RMUX67':[677,693,678,694,679,695,680,681,697,696],
	'RMUX68':[814,830,813,829,812,828,811,810,826,827],
	'RMUX69':[686,702,685,701,684,700,683,682,698,699],
	'RMUX70':[804,820,803,819,802,818,801,800,816,817],
	'RMUX71':[676,692,675,691,674,690,673,672,688,689],
	'RMUX72':[836,852,835,851,834,850,833,832,848,849],
	'RMUX73':[964,980,963,979,962,978,961,960,976,977],
	'RMUX74':[837,853,838,854,839,855,840,841,857,856],
	'RMUX75':[965,981,966,982,967,983,968,969,985,984],
	'RMUX76':[846,862,845,861,844,860,843,842,858,859],
	'RMUX77':[974,990,973,989,972,988,971,970,986,987],
	'RMUX78':[868,884,867,883,866,882,865,864,880,881],
	'RMUX79':[996,1012,995,1011,994,1010,993,992,1008,1009],
	'RMUX80':[869,885,870,886,871,887,872,873,889,888],
	'RMUX81':[997,1013,998,1014,999,1015,1000,1001,1017,1016],
	'RMUX82':[878,894,877,893,876,892,875,874,890,891],
	'RMUX83':[1006,1022,1005,1021,1004,1020,1003,1002,1018,1019],
	'RMUX84':[1029,1045,1030,1046,1031,1047,1032,1033,1049,1048],
	'RMUX85':[901,917,902,918,903,919,904,905,921,920],
	'RMUX86':[1038,1054,1037,1053,1036,1052,1035,1034,1050,1051],
	'RMUX87':[910,926,909,925,908,924,907,906,922,923],
	'RMUX88':[1028,1044,1027,1043,1026,1042,1025,1024,1040,1041],
	'RMUX89':[900,916,899,915,898,914,897,896,912,913],
	'RMUX90':[1061,1077,1062,1078,1063,1079,1064,1065,1081,1080],
	'RMUX91':[933,949,934,950,935,951,936,937,953,952],
	'RMUX92':[1070,1086,1069,1085,1068,1084,1067,1066,1082,1083],
	'RMUX93':[942,958,941,957,940,956,939,938,954,955],
	'RMUX94':[1060,1076,1059,1075,1058,1074,1057,1056,1072,1073],
	'RMUX95':[932,948,931,947,930,946,929,928,944,945],

	'SeamMUX00':[512,513,514,515,516,517,518,519],
	'SeamMUX01':[560,561,562,563,564,565,566,567],
	'SeamMUX02':[520,521,541,522,523,524,525,526],
	'SeamMUX03':[568,569,557,570,571,572,573,574],
}, formatters={
	'RMUX[0-9][0-9]': lambda key,val: mux_format(val, 7, 'I'),
}))
