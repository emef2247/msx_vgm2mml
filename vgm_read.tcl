#!/usr/bin/env tclsh

set script_dir [file dirname [file normalize [info script]]]
source ${script_dir}/scc.tcl
source ${script_dir}/psg.tcl


proc binary_in_hex {bytes} {
	binary scan $bytes h* hexValue
	return $hexValue
}

proc decode_as_integer {bytes} {
	binary scan $bytes i* decodevalue
	return "$decodevalue"
}

proc decode_as_double {bytes} {
	binary scan $bytes d* decodevalue
	return "$decodevalue"
}

proc decode_as_unsigned_int {bytes} {
	# Convert 2bytes binariy into 2bytes hex strings hexStr1 hexStr1 as big endian
	binary scan $bytes H2H2 hexStr1 hexStr2
	set hexUint1 [scan 0x$hexStr1 %x]
	set hexUint2 [scan 0x$hexStr2 %x]
	set decodevalue [expr {$hexUint2 * 256} + $hexUint1]
	puts "decode_as_unsigned_int: hexStr2:$hexStr2 ($hexUint2) hexStr1:$hexStr1 ($hexUint1) decodevalue: $decodevalue"
	return $decodevalue
}


proc decode_as_signed_integer {bytes} {
	binary scan $bytes s* decodevalue
	
	return $decodevalue
}


# 1バイトのバイナリデータを整数に変換する
proc byte_to_integer {binary_data} {
	binary scan $binary_data c* value
	set unsignedValue [expr {0xFF & $value}]
	set fourByteData [binary format I $unsignedValue]

	binary scan $fourByteData I* convertedValue
	return $convertedValue
}


# 4バイトのバイナリ値をBCD形式に変換する関数
proc binary_to_bcd {binary_value} {
    set bcd_value ""
    set binary_str [format %08X $binary_value] ;# 8桁の16進数文字列として表現
    foreach {hex_digit} [split $binary_str ""] {
        set decimal_digit [scan $hex_digit %X]
        lappend bcd_value [format %d $decimal_digit] ;# 各16進数文字を4ビットの2進数に変換
    }
    set string_value [join $bcd_value  ""]
	set numeric_value [scan $string_value %d]
	return $numeric_value
}


set identifier        0
set eof_offset        0
set version           0
set SN76489_clock     0
set YM2413_clock      0
set GD3_offset        0
set total_samples     0
set loop_offset       0
set loop_samples      0
set rate              0
set SNFB              0
set SNW               0
set SF                0
set YM2612_clock      0
set YM2151_clock      0
set VGM_data_offset   0
set Sega_PCM_clock    0
set SPCM_Interface    0
set RF5C68_clock      0
set YM2203_clock      0
set YM2608_clock      0
set YM2610B_clock     0
set YM3812_clock      0
set YM3526_clock      0
set Y8950_clock       0
set YMF262_clock      0
set YMF278B_clock     0
set YMF271_clock      0
set YMZ280B_clock     0
set RF5C164_clock     0
set PWM_clock         0
set AY8910_clock      0
set AYT               0
set AYFlags           0
set VM_xxx_LB_LM      0
set GB_DMG_clock      0
set NES_APU_clock     0
set MultiPCM_clock    0
set uPD7759_clock     0
set OKIM6258_clock    0
set OF                0
set KF                0
set CF                0
set xxx               0
set OKIM6295_clock    0
set K051649_clock     0
set K054539_clock     0
set HuC6280_clock     0
set C140_clock        0
set K053260_clock     0
set Pokey_clock       0
set QSound_clock      0
set SCSP_clock        0
set Extra_Hdr_ofs     0
set WonderSwan_clock  0
set VSU_clock         0
set SAA1099_clock     0
set ES5503_clock      0
set ES5506_clock      0
set ES_chns_CD_xxx    0
set X1010_clock       0
set C352_clock        0
set GA20_clock        0
set Mikey_clock       0

set globa_time        0
set globa_time_stamp  0

proc update_global_time {ticks} {
	variable globa_time
	variable globa_time_stamp
	
	puts "update_global_time globa_time      : $globa_time"
	puts "update_global_time globa_time_stamp: $globa_time_stamp"
	puts "update_global_time ticks           : $ticks"
	puts "update_global_time ticks / 44100.0 : [expr ($ticks / 44100.0)]"
	set globa_time_stamp $globa_time
	set globa_time [expr ($ticks / 44100.0) + $globa_time]
	puts "update_global_time return: $globa_time"
	return $globa_time
}

proc get_global_time {} {
	variable globa_time
	
	return $globa_time
}

	
# 引数のチェック
if {[llength $argv] != 1} {
    puts "Usage: $argv0 <binary file>"
    exit 1
}

# ファイル名を取得
set filename [lindex $argv 0]

# ファイルを開く
set fileId [open $filename "rb"]

#----------------------------------------------------
#  Read first 40 bytes 
#----------------------------------------------------
#0x0
set identifier        [read $fileId 4]
set eof_offset        [read $fileId 4]
set version           [read $fileId 4]
set SN76489_clock     [read $fileId 4]
puts "0x0"
puts "identifier:     $identifier ([binary_in_hex $identifier])"
puts "eof_offset:     [decode_as_integer $eof_offset] ([binary_in_hex $eof_offset])"
puts "version:        [binary_to_bcd [decode_as_integer $version]] ([binary_in_hex $version])"
puts "SN76489_clock:  [decode_as_integer $SN76489_clock] ([binary_in_hex $SN76489_clock])"
puts "#-------------------------------------------------------"

set identifier        $identifier
set eof_offset        [decode_as_integer $eof_offset]
set version           [binary_to_bcd [decode_as_integer $version]]
set SN76489_clock     [decode_as_integer $SN76489_clock]

#0x10
set YM2413_clock  [read $fileId 4]
set GD3_offset    [read $fileId 4]
set total_samples [read $fileId 4]
set loop_offset   [read $fileId 4]

puts "0x10"
puts "YM2413_clock:   [decode_as_integer $YM2413_clock] ([binary_in_hex $YM2413_clock])"
puts "GD3_offset:     [decode_as_integer $GD3_offset] ([binary_in_hex $GD3_offset])"
puts "total_samples:  [decode_as_integer $total_samples] ([binary_in_hex $total_samples])"
puts "loop_offset:    [decode_as_integer $loop_offset] ([binary_in_hex $loop_offset])"
puts "#-------------------------------------------------------"

set YM2413_clock  [decode_as_integer $YM2413_clock]
set GD3_offset    [decode_as_integer $YM2413_clock]
set total_samples [decode_as_integer $YM2413_clock]
set loop_offset   [decode_as_integer $YM2413_clock]

#0x20
set loop_samples      [read $fileId 4]
set rate              [read $fileId 4]
set SNFB              [read $fileId 2]
set SNW               [read $fileId 1]
set SF                [read $fileId 1]
set YM2612_clock      [read $fileId 4]

puts "0x20"
puts "loop_samples:   [decode_as_integer $loop_samples] ([binary_in_hex $loop_samples])"
puts "rate:           [decode_as_integer $rate] ([binary_in_hex $rate])"
puts "SNFB:           [decode_as_signed_integer $SNFB] ([binary_in_hex $SNFB])"
puts "SNW:            [byte_to_integer $SNW] ([binary_in_hex $SNW])"
puts "SF:             [byte_to_integer $SF] ([binary_in_hex $SF])"
puts "YM2612_clock:   [decode_as_integer $YM2612_clock] ([binary_in_hex $YM2612_clock])"
puts "#-------------------------------------------------------"

set loop_samples      [decode_as_integer $loop_samples]
set rate              [decode_as_integer $rate]
set SNFB              [decode_as_signed_integer $SNFB]
set SNW               [byte_to_integer $SNW]
set SF                [byte_to_integer $SF]
set YM2612_clock      [decode_as_integer $YM2612_clock]

#0x30
set YM2151_clock      [read $fileId 4]
set VGM_data_offset   [read $fileId 4]
set Sega_PCM_clock    [read $fileId 4]
set SPCM_Interface    [read $fileId 4]

puts "0x30"
puts "YM2151_clock:    [decode_as_integer $YM2151_clock] ([binary_in_hex $YM2151_clock])"
puts "VGM_data_offset: [decode_as_integer $VGM_data_offset] ([binary_in_hex $VGM_data_offset])"
puts "Sega_PCM_clock:  [decode_as_integer $Sega_PCM_clock] ([binary_in_hex $Sega_PCM_clock])"
puts "SPCM_Interface:  [decode_as_integer $SPCM_Interface] ([binary_in_hex $SPCM_Interface])"
puts "#-------------------------------------------------------"

set YM2151_clock      [decode_as_integer $YM2151_clock]
set VGM_data_offset   [decode_as_integer $VGM_data_offset]
set Sega_PCM_clock    [decode_as_integer $Sega_PCM_clock]
set SPCM_Interface    [decode_as_integer $SPCM_Interface]

# ------------------------------------------------------------
# Read addtional header
# ------------------------------------------------------------
set rest_of_header  [expr $VGM_data_offset - 0x10]
puts "VGM_data_offset: $VGM_data_offset"
puts "rest_of_header: $rest_of_header"

if {$rest_of_header > 0x10} {
#0x40
set RF5C68_clock      [read $fileId 4]
set YM2203_clock      [read $fileId 4]
set YM2608_clock      [read $fileId 4]
set YM2610B_clock     [read $fileId 4]

puts "0x40"
puts "RF5C68_clock:    [decode_as_integer $RF5C68_clock] ([binary_in_hex $RF5C68_clock])"
puts "YM2203_clock:    [decode_as_integer $YM2203_clock] ([binary_in_hex $YM2203_clock])"
puts "YM2608_clock:    [decode_as_integer $YM2608_clock] ([binary_in_hex $YM2608_clock])"
puts "YM2610B_clock:   [decode_as_integer $YM2610B_clock] ([binary_in_hex $YM2610B_clock])"
puts "#-------------------------------------------------------"

set RF5C68_clock      [decode_as_integer $RF5C68_clock]
set YM2203_clock      [decode_as_integer $YM2203_clock]
set YM2608_clock      [decode_as_integer $YM2608_clock]
set YM2610B_clock     [decode_as_integer $YM2610B_clock]
}

if {$rest_of_header > 0x20} {
#0x50
set YM3812_clock      [read $fileId 4]
set YM3526_clock      [read $fileId 4]
set Y8950_clock       [read $fileId 4]
set YMF262_clock      [read $fileId 4]

puts "0x50"
puts "YM3812_clock:    [decode_as_integer $YM3812_clock] ([binary_in_hex $YM3812_clock])"
puts "YM3526_clock:    [decode_as_integer $YM3526_clock] ([binary_in_hex $YM3526_clock])"
puts "Y8950_clock:     [decode_as_integer $Y8950_clock] ([binary_in_hex $Y8950_clock])"
puts "YMF262_clock:    [decode_as_integer $YMF262_clock] ([binary_in_hex $YMF262_clock])"
puts "#-------------------------------------------------------"

set YM3812_clock      [decode_as_integer $YM3812_clock]
set YM3526_clock      [decode_as_integer $YM3526_clock]
set Y8950_clock       [decode_as_integer $Y8950_clock]
set YMF262_clock      [decode_as_integer $YMF262_clock]

}

if {$rest_of_header > 0x30} {
#0x60
set YMF278B_clock     [read $fileId 4]
set YMF271_clock      [read $fileId 4]
set YMZ280B_clock     [read $fileId 4]
set RF5C164_clock     [read $fileId 4]

puts "0x60"
puts "YMF278B_clock:   [decode_as_integer $YMF278B_clock] ([binary_in_hex $YMF278B_clock])"
puts "YMF271_clock:    [decode_as_integer $YMF271_clock] ([binary_in_hex $YMF271_clock])"
puts "YMZ280B_clock:   [decode_as_integer $YMZ280B_clock] ([binary_in_hex $YMZ280B_clock])"
puts "RF5C164_clock:   [decode_as_integer $RF5C164_clock] ([binary_in_hex $RF5C164_clock])"
puts "#-------------------------------------------------------"

set YM3812_clock      [decode_as_integer $YMF278B_clock]
set YM3526_clock      [decode_as_integer $YMF271_clock]
set Y8950_clock       [decode_as_integer $YMZ280B_clock]
set YMF262_clock      [decode_as_integer $RF5C164_clock]

}

if {$rest_of_header > 0x40} {
#0x70
set PWM_clock         [read $fileId 4]
set AY8910_clock      [read $fileId 4]
set AYT               [read $fileId 2]
set AYFlags           [read $fileId 2]
set VM_xxx_LB_LM      [read $fileId 4]

puts "0x70"
puts "PWM_clock:      [decode_as_integer $PWM_clock] ([binary_in_hex $PWM_clock])"
puts "AY8910_clock:   [decode_as_integer $AY8910_clock] ([binary_in_hex $AY8910_clock])"
puts "AYT:            [decode_as_signed_integer $AYT] ([binary_in_hex $AYT])"
puts "AYFlags:        [decode_as_signed_integer $AYFlags] ([binary_in_hex $AYFlags])"
puts "VM_xxx_LB_LM:   [decode_as_integer $VM_xxx_LB_LM] ([binary_in_hex $VM_xxx_LB_LM])"

set PWM_clock         [decode_as_integer $PWM_clock]
set AY8910_clock      [decode_as_integer $AY8910_clock]
set AYT               [decode_as_signed_integer $AYT]
set AYFlags           [decode_as_signed_integer $AYFlags]
set VM_xxx_LB_LM      [decode_as_integer $VM_xxx_LB_LM]

puts "#-------------------------------------------------------"
}

if {$rest_of_header > 0x60} {
#0x80
set GB_DMG_clock      [read $fileId 4]
set NES_APU_clock     [read $fileId 4]
set MultiPCM_clock    [read $fileId 4]
set uPD7759_clock     [read $fileId 4]

puts "0x80"
puts "GB_DMG_clock:   [decode_as_integer $GB_DMG_clock] ([binary_in_hex $GB_DMG_clock])"
puts "NES_APU_clock:  [decode_as_integer $NES_APU_clock] ([binary_in_hex $NES_APU_clock])"
puts "MultiPCM_clock: [decode_as_integer $MultiPCM_clock] ([binary_in_hex $MultiPCM_clock])"
puts "uPD7759_clock:  [decode_as_integer $uPD7759_clock] ([binary_in_hex $uPD7759_clock])"
puts "#-------------------------------------------------------"

set GB_DMG_clock      [decode_as_integer $GB_DMG_clock]
set NES_APU_clock     [decode_as_integer $NES_APU_clock]
set MultiPCM_clock    [decode_as_integer $MultiPCM_clock]
set uPD7759_clock     [decode_as_integer $uPD7759_clock]

}

if {$rest_of_header > 0x70} {
#0x90
set OKIM6258_clock    [read $fileId 4]
set OF                [read $fileId 1]
set KF                [read $fileId 1]
set CF                [read $fileId 1]
set xxx               [read $fileId 1]
set OKIM6295_clock    [read $fileId 4]
set K051649_clock     [read $fileId 4]

puts "0x90"
puts "OKIM6258_clock: [decode_as_integer $OKIM6258_clock] ([binary_in_hex $OKIM6258_clock])"
puts "OF:             [byte_to_integer $OF] ([binary_in_hex $OF])"
puts "KF:             [byte_to_integer $KF] ([binary_in_hex $KF])"
puts "CF:             [byte_to_integer $CF] ([binary_in_hex $CF])"
puts "xxx:            [byte_to_integer $xxx] ([binary_in_hex $xxx])"
puts "OKIM6295_clock: [decode_as_integer $OKIM6295_clock] ([binary_in_hex $OKIM6295_clock])"
puts "K051649_clock:  [decode_as_integer $K051649_clock] ([binary_in_hex $K051649_clock])"
puts "#-------------------------------------------------------"

set OKIM6258_clock    [decode_as_integer $OKIM6258_clock]
set OF                [byte_to_integer $OF]
set KF                [byte_to_integer $KF]
set CF                [byte_to_integer $CF]
set xxx               [byte_to_integer $xxx]
set OKIM6295_clock    [decode_as_integer $OKIM6295_clock]
set K051649_clock     [decode_as_integer $K051649_clock]

}

if {$rest_of_header > 0x80} {
#0xA0
set K054539_clock     [read $fileId 4]
set HuC6280_clock     [read $fileId 4]
set C140_clock        [read $fileId 4]
set K053260_clock     [read $fileId 4]

puts "0xA0"
puts "K054539_clock:  [decode_as_integer $K054539_clock] ([binary_in_hex $K054539_clock])"
puts "HuC6280_clock:  [decode_as_integer $HuC6280_clock] ([binary_in_hex $HuC6280_clock])"
puts "C140_clock:     [decode_as_integer $C140_clock] ([binary_in_hex $C140_clock])"
puts "K053260_clock:  [decode_as_integer $K053260_clock] ([binary_in_hex $K053260_clock])"
puts "#-------------------------------------------------------"
}

if {$rest_of_header > 0x90} {
#0xB0
set Pokey_clock       [read $fileId 4]
set QSound_clock      [read $fileId 4]
set SCSP_clock        [read $fileId 4]
set Extra_Hdr_ofs     [read $fileId 4]

puts "0xB0"
puts "Pokey_clock:    [decode_as_integer $Pokey_clock] ([binary_in_hex $Pokey_clock])"
puts "QSound_clock:   [decode_as_integer $QSound_clock] ([binary_in_hex $QSound_clock])"
puts "SCSP_clock:     [decode_as_integer $SCSP_clock] ([binary_in_hex $SCSP_clock])"
puts "Extra_Hdr_ofs:  [decode_as_integer $Extra_Hdr_ofs] ([binary_in_hex $Extra_Hdr_ofs])"
puts "#-------------------------------------------------------"
}

if {$rest_of_header > 0xA0} {
#0xC0
set WonderSwan_clock  [read $fileId 4]
set VSU_clock         [read $fileId 4]
set SAA1099_clock     [read $fileId 4]
set ES5503_clock      [read $fileId 4]

puts "0xC0"
puts "WonderSwan_clock: [decode_as_integer $WonderSwan_clock] ([binary_in_hex $WonderSwan_clock])"
puts "VSU_clock:        [decode_as_integer $VSU_clock] ([binary_in_hex $VSU_clock])"
puts "SAA1099_clock:    [decode_as_integer $SAA1099_clock] ([binary_in_hex $SAA1099_clock])"
puts "ES5503_clock:     [decode_as_integer $ES5503_clock] ([binary_in_hex $ES5503_clock])"
puts "#-------------------------------------------------------"

}

if {$rest_of_header > 0xB0} {
#0xD0
set ES5506_clock      [read $fileId 4]
set ES_chns_CD_xxx    [read $fileId 4]
set X1010_clock       [read $fileId 4]
set C352_clock        [read $fileId 4]

puts "0xD0"
puts "ES5506_clock:   [decode_as_integer $ES5506_clock] ([binary_in_hex $ES5506_clock])"
puts "ES_chns_CD_xxx: [decode_as_integer $ES_chns_CD_xxx] ([binary_in_hex $ES_chns_CD_xxx])"
puts "X1010_clock:    [decode_as_integer $X1010_clock] ([binary_in_hex $X1010_clock])"
puts "C352_clock:     [decode_as_integer $C352_clock] ([binary_in_hex $C352_clock])"
puts "#-------------------------------------------------------"

}

if {$rest_of_header > 0xC0} {
#0xE0
set GA20_clock        [read $fileId 4]
set Mikey_clock       [read $fileId 4]

puts "0x#0"
puts "GA20_clock:    [decode_as_integer $GA20_clock] ([binary_in_hex $GA20_clock])"
puts "Mikey_clock:   [decode_as_integer $Mikey_clock] ([binary_in_hex $Mikey_clock])"
puts "#-------------------------------------------------------"

# 0x50	dd	PSG (SN76489/SN76496) write value dd
# 0x51	aa dd	YM2413, write value dd to register aa
# 0x52	aa dd	YM2612 port 0, write value dd to register aa
# 0x53	aa dd	YM2612 port 1, write value dd to register aa
# 0x54	aa dd	YM2151, write value dd to register aa
# 0x55	aa dd	YM2203, write value dd to register aa
# 0x56	aa dd	YM2608 port 0, write value dd to register aa
# 0x57	aa dd	YM2608 port 1, write value dd to register aa
# 0x58	aa dd	YM2610 port 0, write value dd to register aa
# 0x59	aa dd	YM2610 port 1, write value dd to register aa
# 0x5A	aa dd	YM3812, write value dd to register aa
# 0x5B	aa dd	YM3526, write value dd to register aa
# 0x5C	aa dd	Y8950, write value dd to register aa
# 0x5D	aa dd	YMZ280B, write value dd to register aa
# 0x5E	aa dd	YMF262 port 0, write value dd to register aa
# 0x5F	aa dd	YMF262 port 1, write value dd to register aa
# 

# 0x61	nn nn	Wait n samples, n can range from 0 to 65535 (approx 1.49 seconds). Longer pauses than this are represented by multiple wait commands.
# 0x62		wait 735 samples (60th of a second), a shortcut for 0x61 0xdf 0x02
# 0x63		wait 882 samples (50th of a second), a shortcut for 0x61 0x72 0x03
# 0x66		end of sound data
# 0x67	...	data block: see below
# 0x68	...	PCM RAM write: see below
# 0x7n		wait n+1 samples, n can range from 0 to 15
# 
# 0xB4	aa dd	NES APU, write value dd to register aa
# 		Note: Registers 00-1F equal NES address 4000-401F, registers 20-3E equal NES address 4080-409E, register 3F equals NES address 4023, registers 40-7F equal NES address 4040-407F
# 0xA0	aa dd       AY8910, write value dd to register aa
# 0xD2	pp aa dd	SCC1, port pp, write value dd to register aa
# 0xD3	pp aa dd	K054539, write value dd to register ppaa

}

set done_bytes [expr 0x40 + $rest_of_header]
set data_size [expr $eof_offset + 4 - $done_bytes]

::scc::init 0
::psg::init 0

#while {[eof $fileId] == 0} {
while {$done_bytes < $data_size} {
	set command    [read $fileId 1]
	set cmd_int [byte_to_integer $command]
	incr done_bytes
	
	puts "$done_bytes / $data_size command: [format %x $cmd_int] ($cmd_int) (binary: [binary_in_hex $command])"
	if { $cmd_int == 0x61} {
		set nn [read $fileId 2]
		incr done_bytes
		incr done_bytes
		set nn_int [decode_as_unsigned_int $nn]
		set nn_str [binary_in_hex $nn]
		set time_in_s [update_global_time $nn_int]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
		puts "nn_int: $nn_int nn_str: $nn_str"
	} elseif { $cmd_int == 0x62} {
		puts "0x62		wait 735 samples (60th of a second)"
		set time_in_s [expr 735 / 44100.0]
		set time_in_s [update_global_time 735]
		set time_in_ticks_60int [expr $time_in_s * 60]
		puts "	time_in_s: $time_in_s time_in_ticks_60int:$time_in_ticks_60int"
	} elseif { $cmd_int == 0x63} {
		puts "0x63		wait 882 samples (50th of a second)"
		set time_in_s [expr 882 / 44100.0]
		set time_in_s [update_global_time 882]
		set time_in_ticks_60int [expr $time_in_s * 60]
		puts "	time_in_s: $time_in_s time_in_ticks_60int:$time_in_ticks_60int"
	} elseif { $cmd_int == 0x66} {
		puts "0x66		end of sound data"
	} elseif { $cmd_int == 0x67} {
		puts "0x67	...	data block"
	} elseif { $cmd_int == 0x68} {
		puts "0x68	...	PCM RAM write"
	} elseif { $cmd_int == 0x70} {
		puts "0x70		wait 0+1 samples"
		set time_in_s [update_global_time 1]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x71} {
		puts "0x71		wait 1+1 samples"
		set time_in_s [update_global_time 2]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x72} {
		puts "0x72		wait 2+1 samples"
		set time_in_s [update_global_time 3]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x73} {
		puts "0x73		wait 3+1 samples"
		set time_in_s [update_global_time 4]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x74} {
		puts "0x74		wait 4+1 samples"
		set time_in_s [update_global_time 5]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x75} {
		set time_in_s [update_global_time 6]
		set time_in_s [expr 6 / 44100.0]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x76} {
		set time_in_s [update_global_time 7]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x77} {
		puts "0x77		wait 7+1 samples"
		set time_in_s [expr 8 / 44100.0]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x78} {
		puts "0x78		wait 8+1 samples"
		set time_in_s [update_global_time 9]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x79} {
		puts "0x79		wait 9+1 samples"
		set time_in_s [update_global_time 10]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x7a} {
		puts "0x7a		wait 10+1 samples"
		set time_in_s [expr 11 / 44100.0]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x7b} {
		puts "0x7b		wait 11+1 samples"
		set time_in_s [update_global_time 12]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x7c} {
		puts "0x7c		wait 12+1 samples"
		set time_in_s [update_global_time 13]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x7d} {
		puts "0x7d		wait 131+1 samples"
		set time_in_s [update_global_time 14]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x7e} {
		puts "0x7e		wait 14+1 samples"
		set time_in_s [update_global_time 15]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0x7f} {
		puts "0x7f		wait 15+1 samples"
		set time_in_s [update_global_time 16]
		set time_in_ticks_60int [expr int($time_in_s * 60)]
	} elseif { $cmd_int == 0xB4} {
	} elseif { $cmd_int == 0xA0} {
		#AY8910, write value dd to register aa
		set time [get_global_time]
		set ticks [expr int($time * 60)]
		set aa [read $fileId 1]
		incr done_bytes
		set dd [read $fileId 1]
		incr done_bytes
		set aa_int [byte_to_integer $aa]
		set dd_int [byte_to_integer $dd]
		puts "$time ($ticks) 0xA0	[binary_in_hex $aa] [binary_in_hex $dd]	AY8910, write value [format 0x%x $dd_int] ($dd_int) to register [format 0x%02x $aa_int] ($aa_int)"
		# A0H～A3H
		set wp_last_address $aa_int
		set wp_last_value $dd_int
		
		::psg::write [get_global_time] $wp_last_address $wp_last_value
	} elseif { $cmd_int == 0xD2} {
		#	SCC1, port pp, write value dd to register aa
		set time [get_global_time]
		set ticks [expr int($time * 60)]
		set pp [read $fileId 1]
		incr done_bytes
		set aa [read $fileId 1]
		incr done_bytes
		set dd [read $fileId 1]
		incr done_bytes
		set pp_int [byte_to_integer $pp]
		set aa_int [byte_to_integer $aa]
		set dd_int [byte_to_integer $dd]
		puts "$time ($ticks) 0xD2	[binary_in_hex $pp] [binary_in_hex $aa] [binary_in_hex $dd]	SCC1, port [format %x $pp_int], write value [format %x $dd_int] to register [format 0x%02x $aa_int]"
		
		set wp_last_address 0
		set wp_last_value $dd_int
		switch $pp_int {
			0 { set wp_last_address [expr 0x9800 + $aa_int]}
			1 { set wp_last_address [expr 0x9880 + $aa_int]}
			2 { set wp_last_address [expr 0x988A + $aa_int]}
			3 { set wp_last_address [expr 0x988F + $aa_int]}
			default { puts "無効な値です: $pp_int" }
		}
		
		puts "0xD2 $pp_int $aa_int $dd_int :[format 0x%4x $wp_last_address] [format %x $wp_last_value] ($wp_last_value)"
		::scc::write_scc [get_global_time] $wp_last_address $wp_last_value
		
	} elseif { $cmd_int == 0xD3} {
		set time [get_global_time]
		set ticks [expr int($time * 60)]
		set pp [read $fileId 1]
		incr done_bytes
		set aa [read $fileId 1]
		incr done_bytes
		set dd [read $fileId 1]
		incr done_bytes
		set pp_int [byte_to_integer $pp]
		set aa_int [byte_to_integer $aa]
		set dd_int [byte_to_integer $dd]
	}
}

set directory $script_dir
#variable directory [file normalize $::env(OPENMSX_USER_DATA)/../vgm_recordings]
::scc::output_csv $directory $filename
::psg::outputCsv $directory $filename


# ファイルを閉じる
close $fileId
