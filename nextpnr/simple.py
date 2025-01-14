#
# Copyright 2020 Steve White
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
import sys
import os
sys.path.append(os.path.join('..', 'bitstream'))

from chips import ChipWithID, ChipOrPackageNamed

chip_id_env = 'AGM_DEVICE'

if not chip_id_env in os.environ:
    chip = ChipWithID(0x00120010)
else:
    chip = ChipOrPackageNamed(os.environ[chip_id_env])

def nameForTile(tile, row, col):
    return "%s(%02i,%02i)" % (tile.type, col, row)

def createTileBELs(chip, tile, row, col):
    tile_name = nameForTile(tile, row, col)
    def io_str_parse(str, bad_wires):
        if str[-1] != ']':
            return (str, 0)
        openb = str.rfind("[")
        bits = str[openb+1:-1]
        colon = bits.find(":")
        high = int(bits[:colon])
        low = int(bits[colon+1])
        name = str[:openb]
        if bad_wires:
            if type(bad_wires) == bool:
                return (name, 0)
            elif type(bad_wires) == list and name in bad_wires:
                return (name, 0)
        return (name, high)
    
    for bel_info in tile.bels:
        name = bel_info['name']
        btype = bel_info.get('type', name)
        num_slices = bel_info['count']
        inputs = bel_info['inputs']
        outputs = bel_info['outputs']
        aliases = bel_info.get('aliases',{})
        mappings = bel_info.get('wire_map',{})
        pseudo = bel_info.get('pseudo', False)
        gb = bel_info.get('gb', False)
        # Wire DB isn't correct for everything yet...
        bad_wires = bel_info.get('bad_wires', None)
        
        for slice in range(0, num_slices):
            if num_slices > 1:
                bel_name = "%s:%s%02i" % (tile_name, name, slice)
            else:
                bel_name = tile_name
            
            if not pseudo:
                #print("Adding bel:%s type:%s x:%s y:%s z:%s" % (bel_name, btype, col, row, slice))
                ctx.addBel(name=bel_name, type=btype, loc=Loc(col, row, slice), gb=gb)
            wire_base = "%s:%s%02i" % (tile_name, name, slice)
            
            #
            # Inputs
            #
            for an_input in inputs:
                (name_base, count) = io_str_parse(an_input, bad_wires)
                for idx in range(0, count+1):
                    if count == 0:
                        pin_name = name_base
                    else:
                        pin_name = "%s[%i]" % (name_base, idx)
                    
                    if pin_name in mappings:
                        wire = "%s:%s%02i" % (tile_name, mappings[pin_name], slice)
                    else:
                        wire = "%s:%s" % (wire_base, pin_name)

                    if not "MUX" in wire:
                        #print("input wire %s" % (wire))
                        addWire(row, col, wire)
                    if not pseudo:
                        ctx.addBelInput(bel=bel_name, name=aliases.get(pin_name, pin_name), wire=wire)
            
            #
            # Outputs
            #
            for an_output in outputs:
                (name_base, count) = io_str_parse(an_output, bad_wires)
                for idx in range(0, count+1):
                    if count == 0:
                        pin_name = name_base
                    else:
                        pin_name = "%s[%i]" % (name_base, idx)
                    
                    if pin_name in mappings:
                        wire = "%s:%s%02i" % (tile_name, mappings[pin_name], slice)
                    else:
                        wire = "%s:%s" % (wire_base, pin_name)

                    if not "MUX" in wire:
                        #print("output wire %s" % (wire))
                        addWire(row, col, wire)
                    if not pseudo:
                        ctx.addBelOutput(bel=bel_name, name=aliases.get(pin_name, pin_name), wire=wire)
                    #
                    # Automatically connect pseudo in+outs
                    #
                    else:
                        base = None
                        head = None
                        if name_base.lower().endswith("out"):
                            base = name_base[:-3]
                            head = True
                        elif name_base.lower().startswith("out"):
                            base = name_base[3:]
                            head = False
                        if head == None:
                            continue
                        
                        for an_input in inputs:
                            if (head and an_input.startswith(base)) or (not head and an_input.endswith(base)):
                                if an_input[-1] == ']':
                                    an_input = an_input[0:an_input.index('[')]
                                sink = "%s:%s" % (wire_base, an_input)
                                createAlias(sink, wire, row, col)
                                break
    
# This would be an alta_rio in AGM speak
def createIOTile(chip, tile, row, col):
    assert row < chip.rows
    assert col < chip.columns 
    tile_name = nameForTile(tile, row, col)
    
    # Temporary kludge while IO tile BELs are
    # being migrated into tiles.py
    existing_bels = ctx.getBels()
    for bel_id in existing_bels:
        if bel_id.startswith(tile_name):
            return

    for z in range(0, tile.slices):
        belname = "%s:alta_rio%02i" % (tile_name, z)
        gb = "GclkDMUX00" in tile.values
        #print("Creating bel: %s" % belname)
        ctx.addBel(name=belname, type="GENERIC_IOB", loc=Loc(col, row, z), gb=gb)
        
        regs = ['combout', 'regout', 'paddataout']
        oname = None
        for reg_name in regs:
            if tile.name.startswith('agm'):
                name = "alta_dioreg%02i:%s" % (z, reg_name)
            else:
                name = "alta_ioreg%02i:%s" % (z, reg_name)
            wire = "%s:%s" % (tile_name, name)
            addWire(row, col, wire)
            if reg_name == 'combout':
                oname = wire
            
        ios = ['combout']
        for io_name in ios:
            name = "alta_io%02i:%s" % (z, io_name)
            wire = "%s:%s" % (tile_name, name)
            addWire(row, col, wire)
        
        iname = "%s:IOMUX%02i" % (tile_name, z)
        oename = "%s:oe%02i" % (tile_name, z)
        
        # iname and oname wires are already created
        addWire(row, col, oename)
        
        ctx.addBelInput(bel=belname, name="I", wire=iname)
        ctx.addBelInput(bel=belname, name="EN", wire=oename)
        ctx.addBelOutput(bel=belname, name="O", wire=oname)    
        
def createPIP(pip_name, pip_type, wire_src, wire_dest, delay, row, col):
    assert row < chip.rows
    assert col < chip.columns 
    #print("createPIP(%s, %s, %s, %s, %s, %s, %s)" % (pip_name, pip_type, wire_src, wire_dest, delay, row, col))
    try:
        ctx.addPip(
            name=pip_name, type=pip_type, srcWire=wire_src, dstWire=wire_dest,
            delay=ctx.getDelayFromNS(delay), loc=Loc(col, row, 0))
    except IndexError as e:
        print("createPIP: name=%s => %s" % (pip_name, e))
        pass
    except AssertionError as e:
        print("createPIP: name=%s => %s" % (pip_name, e))
        pass

def createAlias(src, dest, row, col):
    createPIP("%s <= %s" % (src, dest), "alias", src, dest, 0, row, col)
    

def addWire(row, col, name, typ=""):
    #print("addWire(%s, %s, %s, %s)" % (row, col, name, typ))
    assert row < chip.rows
    assert col < chip.columns 
    try:
        ctx.addWire(name=name, type=typ, y=row, x=col)
    except AssertionError as e:
        print("addWire: name=%s, y=%i, x=%i => %s" % (name, row, col, e))
        pass

#
# Create wires and BELs
#
print("Creating wires and BELs")
for row in range(0, chip.rows):
    for col in range(0, chip.columns):
        tile = chip.tile_at(col, row)
        if tile is None:
            continue
        
        ttype = tile.type
        pseudos = tile.pseudos
        for prefix in pseudos:
            count = pseudos[prefix]
            for num in range(0, count):
                key = "%s%02i" % (prefix, num)
                addWire(row, col, "%s(%02i,%02i):%s" % (ttype, col, row, key), "O0")

        for key in tile.values:
            if not "MUX" in key:
                continue

            addWire(row, col, "%s(%02i,%02i):%s" % (ttype, col, row, key), "O0")
        
        if tile.bels:
            createTileBELs(chip, tile, row, col)
        if ttype == "IOTILE":
            createIOTile(chip, tile, row, col)

#
# Create Programmable Interconnect Points and Wires
# Wire: a fixed physical connection inside the FPGA between Pips and/or Bel pins.
# Pip: Programmable Interconnect Point, a configurable connection in one direction between two wires
#

print("Creating PIPs")
def wire_enumerator(wire):
    source = wire.source
    dest = wire.dest
    
    assert source.row < chip.rows
    assert dest.row < chip.rows
    assert source.col < chip.columns
    assert dest.col < chip.columns
    
    createPIP(wire.name, wire.wire_type, source.name, dest.name, wire.delay, dest.row, dest.col)

chip.wire_db.enumerate_all_wires(wire_enumerator)
