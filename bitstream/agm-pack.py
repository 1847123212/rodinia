#!/usr/bin/python
#
# Copyright 2019 Steve White
#
# Permission is hereby granted, free of charge, to any person obtaining 
# a copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included 
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL 
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.
#

import sys
import argparse

from bwriter import BinaryWriter
from crc import crc
from chips import ChipWithID, chips
from utils import round_up

parser = argparse.ArgumentParser(description='Creates AltaGate binary bitstreams from textual bitstreams')
parser.add_argument('input', metavar='input', type=str,
                    help='The input textual bitstream file')
parser.add_argument('output', metavar='output', type=str,
                    help='The output binary bitstream file')
parser.add_argument('--spi', dest='spi_flash', action='store_true',
                    help="Outputs binary suitable for SPI flash memory")
                    

args = parser.parse_args()

with open(args.input, "r") as file:
    lines = file.readlines()

#
# Parse the .asc file
#
entries = []
data = None
chip = None
for line in lines:
    line = line.strip()
    if line.startswith("."):
        data = None
        comps = line.split(" ")
        if len(comps) == 2:
            if comps[0] == ".device":
                chip_id = int(comps[1], 16)
                chip = ChipWithID(chip_id)
            elif comps[0] == ".config_chain":
                chain_id = int(comps[1])
                data = { 'bits': [], 'type': 'chain', 'id': chain_id }
                entries.append(data)
        if len(comps) == 3:
            if chip != None:
                x = int(comps[1])
                y = int(comps[2])
                if x >= 0 and y >= 0:
                    data = {'x': x, 'y': y, 'type': 'tile', 'bits': []}
                    entries.append(data)
    elif len(line) > 0:
        if data != None:
            for char in line:
                if char == "0" or char == "1":
                    data['bits'].append(int(char))

#
# Helpers for retrieving parsed data
#
def chain_with_id(id):
    for entry in entries:
        if entry['type'] != 'chain':
            continue
        if entry['id'] == id:
            return entry
    return None
    
def tile_at_coord(x,y):
    for entry in entries:
        if entry['type'] != 'tile':
            continue
        if entry['x'] == x and entry['y'] == y:
            return entry
    return None
    

#
# Writing...
#
writer = BinaryWriter()
if chip.device_id == 0x01500010:
    # Unsure what this does, but it appears to be important...
    writer.write32(0x967E3C5A)

writer.write32(chip.device_id)
writer.write32(0x0000FFFF)

if chip.device_id == 0x01000001 or chip.device_id == 0x01500010:
    # 0x55030000 appears on lzw bitstreams
    # 0x00030000 appears when lzw is disabled
    writer.write32(0x00030000)
    while writer.length() < 32:
        writer.write32(0x00000000)
    # Register header, write address 6
    writer.write32(0x2200FC06)
    # Reg data: 00000022
    writer.write32(0x00000022)

def write_register_data(reg, len, data):
    writer.write32(0xA2000000 | reg)
    writer.write32(((len - 1) << 8) | 0x20)
    writer.writeBits(data)

#
# Enumerate config chains
#
for chain_id in range(0, len(chip.configChain)):
    chain = chain_with_id(chain_id)
    chain_bits = chain['bits']
    chain_len = len(chain_bits)
    exp_len = len(chip.configChain[chain_id].empty_bits())
    
    if chip.device_id == 0x01500010 and exp_len == chain_len:
        chain_bits = [chain_bits[int(x/4)] for x in range(0, len(chain_bits) * 4)]
        chain_len = len(chain_bits)

    num_padding_bits = round_up(chain_len, 32) - chain_len

    write_register_data(0x20 | chain_id, chain_len, chain_bits + ([0] * num_padding_bits))

#
# Write the bitstream
#
bitstream = []
for tile_row in range(chip.rows - 1,-1,-1):
    row_height = chip.bitstream_height_for_row(tile_row)
    
    for row in range(0, row_height):    
        row_bits = []
        for tile_col in range(chip.columns - 1,-1,-1):
            column_width = chip.bitstream_width_for_column(tile_col)
            tile = chip.tile_at(tile_col, tile_row)
            
            entry = tile_at_coord(tile_col, tile_row)
            if entry is None:
                bits = [1] * column_width
            else:
                offset = tile.bitstream_width * row
                bits = entry['bits'][offset:offset+tile.bitstream_width]
                if len(bits) < column_width:
                    padding = [1] * (column_width - len(bits))
                    bits = padding + bits
            
            row_bits += bits[::-1]
        
        assert(chip.bitstream_row_width() == len(row_bits))

        row_width = round_up(len(row_bits), 8)        
        rounded_row_width = int(((row_width / 32) + 1) * 32)
        
        num_padding_bits = rounded_row_width - len(row_bits)
        
        row_bits += [0] * num_padding_bits
        bitstream += row_bits


index = 0
while len(bitstream) > 0:
    # The AG10K bitstream comes in two chunks, one 
    # with 1394432 bits, the other with 1281280 bits
    # This is to emulate that behavior
    if chip.device_id == 0x01500010:
        max_len = 2186240
    else:
        max_len = 1394432
    
    write_register_data(index, min(max_len, len(bitstream)), bitstream[:max_len])
    bitstream = bitstream[max_len:]
    index += 1

#
# Write the checksum
#
writer.write32(0x2A00FC02)
writer.write32(0x00000F8F)
writer.write32(crc(writer.getBytes()))

with open(args.output, "wb") as binfile:
    if args.spi_flash:
        spi_flash_header = [0x55,0x55,0x00,0x00,0x0E,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]
        binfile.write(bytearray(spi_flash_header))

    binfile.write(writer.getBytes())
