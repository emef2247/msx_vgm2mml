namespace eval ::mml_util {
	# --- File Stamp ---
    #set file_stamp [clock format [clock seconds] -format {%Y_%m%d_%H%M%S}]
	
	# --- Directories ---
    set script_dir [file tail [file dirname [file normalize [info script]]]]
	
    #set script_dir ".\/$script_dir"
    set dir_path   [file dirname $script_dir]
    set csv_dir    ${dir_path}/csv
    set output_dir ${dir_path}/output
    set source_dir ${dir_path}/atrace_files
    set lib_dir    ${dir_path}/libs
	
	# --- For debug ---
	set debug_level 1
	
	# --- File handle ---
    set outf_tcl 0

	set output_name_body test
	
	# --- misc variables ---
	set next_all0_flg     0
	set start_to_read_flg 0
	set begin_flg 0
	set refcount_flg 0
	set line_number 0
	set last_buffer ""
	
	# --- misc variables ---
	set start_to_read_flg 0
	set line_number 0
	set last_buffer ""
	
	# --- List of Table key ---
	set cpuid_list ""
	
	# --- List of Table key ---
	set command_pid_list ""
	set command_pid_list ""
	set command_list ""
	
	variable num_of_ch 4
	variable tempo 225
	variable l64 0
	variable chOffset 4
	
	array set logBuffer {}
	array set workBuffer1 {}
	array set workBuffer2 {}
	array set mmlBuffer1 {}
	array set mmlBuffer1F {}
	array set adjustment {}
	
	array set IntermediateBufferForMML {}
	array set IntermediateBufferForMML2 {}
	
	variable waveTableBufferForMML [list]
	variable envelopBufferForMML [list]
	variable headerBufferForMML [list]
	
	variable vStamp 0
	variable num_mml 0
	variable mmlLineBuffer ""
	variable mmlType ""
	variable mmlFreq 0
	variable mmlCh 0
	variable mmlV 0
	variable mmlOctave 0
	variable mmlTone 0
	variable mmlDelta 0
	variable mmlL 0
	variable mmlLCnt 0
	variable mmlWtblIndex 0
	variable mmlEnvByte  ""
	variable mmlEnvIndex 0
	
	variable mmlTypePrev  ""
	variable mmlFreqPrev 0
	variable mmlChPrev 0
	variable mmlVPrev 0
	variable mmlOctavePrev 0
	variable mmlTonePrev 0
	variable mmlDeltaPrev 0
	variable mmlLPrev 0
	variable mmlLCntPrev 0
	variable mmlWtblIndexPrev 0
	variable mmlEnvBytePrev 0
	variable mmlEnvIndexPrev 0
	variable mmlvDiffPrev 0
	
	variable refLCntStamp 0
	

		
	# --- Table Definition ---
	

	
	# --- File Handle Descriptor ---
	set fd 0

	proc init {} {
		variable chOffset 4
		variable tempo 225
		variable l64 [expr (60.0 / $tempo) / 16]
		variable next_all0_flg 0
		variable newline_flg 1
		variable vStamp 0
		variable num_mml 0
		variable mmlLineBuffer ""
		variable mmlFreq 0
		variable mmlType ""
		variable mmlCh 0
		variable mmlV 0
		variable mmlOctave 0
		variable mmlTone 0
		variable mmlDelta 0
		variable mmlL 0
		variable mmlLCnt 0
		variable mmlWtblIndex 0
		variable mmlEnvByte  ""
		variable mmlEnvIndex 0
		
		variable mmlTypePrev  ""
		variable mmlFreqPrev 0
		variable mmlChPrev 0
		variable mmlVPrev 0
		variable mmlOctavePrev 0
		variable mmlTonePrev 0
		variable mmlDeltaPrev 0
		variable mmlLPrev 0
		variable mmlLCntPrev 0
		variable mmlWtblIndexPrev 0
		variable mmlEnvBytePrev 0
		variable mmlEnvIndexPrev 0
		
		for {set ch 0} {$ch < $::mml_util::num_of_ch} {incr ch} {
			set ::mml_util::adjustment($ch) 0
			set ::mml_util::logBuffer($ch) ""
		 	set ::mml_util::workBuffer1($ch) ""
		 	set ::mml_util::workBuffer2($ch) ""
		 	set ::mml_util::mmlBuffer1($ch) ""
		 	set ::mml_util::mmlBuffer1F($ch) ""
	
			set ::mml_util::IntermediateBufferForMML($ch) ""
			set ::mml_util::IntermediateBufferForMML2($ch) ""
		}
	
		set ::mml_util::waveTableBufferForMML [list]
		set ::mml_util::envelopBufferForMML [list]
		set ::mml_util::headerBufferForMML [list]
	
	}
	
	# PSG Tone Table		
	set reg2tone [dict create]		
	dict set reg2tone	3421	o1c
	dict set reg2tone	3228	o1c+
	dict set reg2tone	3047	o1d
	dict set reg2tone	2876	o1d+
	dict set reg2tone	2715	o1e
	dict set reg2tone	2562	o1f
	dict set reg2tone	2419	o1f+
	dict set reg2tone	2283	o1g
	dict set reg2tone	2155	o1g+
	dict set reg2tone	2034	o1a
	dict set reg2tone	1920	o1a+
	dict set reg2tone	1812	o1b
	dict set reg2tone	1711	o2c
	dict set reg2tone	1614	o2c+
	dict set reg2tone	1524	o2d
	dict set reg2tone	1438	o2d+
	dict set reg2tone	1358	o2e
	dict set reg2tone	1281	o2f
	dict set reg2tone	1210	o2f+
	dict set reg2tone	1142	o2g
	dict set reg2tone	1078	o2g+
	dict set reg2tone	1017	o2a
	dict set reg2tone	960	o2a+
	dict set reg2tone	906	o2b
	dict set reg2tone	855	o3c
	dict set reg2tone	807	o3c+
	dict set reg2tone	762	o3d
	dict set reg2tone	719	o3d+
	dict set reg2tone	679	o3e
	dict set reg2tone	641	o3f
	dict set reg2tone	605	o3f+
	dict set reg2tone	571	o3g
	dict set reg2tone	539	o3g+
	dict set reg2tone	509	o3a
	dict set reg2tone	480	o3a+
	dict set reg2tone	453	o3b
	dict set reg2tone	428	o4c
	dict set reg2tone	404	o4c+
	dict set reg2tone	381	o4d
	dict set reg2tone	360	o4d+
	dict set reg2tone	339	o4e
	dict set reg2tone	320	o4f
	dict set reg2tone	302	o4f+
	dict set reg2tone	285	o4g
	dict set reg2tone	269	o4g+
	dict set reg2tone	254	o4a
	dict set reg2tone	240	o4a+
	dict set reg2tone	227	o4b
	dict set reg2tone	214	o5c
	dict set reg2tone	202	o5c+
	dict set reg2tone	190	o5d
	dict set reg2tone	180	o5d+
	dict set reg2tone	170	o5e
	dict set reg2tone	160	o5f
	dict set reg2tone	151	o5f+
	dict set reg2tone	143	o5g
	dict set reg2tone	135	o5g+
	dict set reg2tone	127	o5a
	dict set reg2tone	120	o5a+
	dict set reg2tone	113	o5b
	dict set reg2tone	107	o6c
	dict set reg2tone	101	o6c+
	dict set reg2tone	95	o6d
	dict set reg2tone	90	o6d+
	dict set reg2tone	85	o6e
	dict set reg2tone	80	o6f
	dict set reg2tone	76	o6f+
	dict set reg2tone	71	o6g
	dict set reg2tone	67	o6g+
	dict set reg2tone	64	o6a
	dict set reg2tone	60	o6a+
	dict set reg2tone	57	o6b
	dict set reg2tone	53	o7c
	dict set reg2tone	50	o7c+
	dict set reg2tone	48	o7d
	dict set reg2tone	45	o7d+
	dict set reg2tone	42	o7e
	dict set reg2tone	40	o7f
	dict set reg2tone	38	o7f+
	dict set reg2tone	36	o7g
	dict set reg2tone	34	o7g+
	dict set reg2tone	32	o7a
	dict set reg2tone	30	o7a+
	dict set reg2tone	28	o7b
	dict set reg2tone	27	o8c
	dict set reg2tone	25	o8c+
	dict set reg2tone	24	o8d
	dict set reg2tone	22	o8d+
	dict set reg2tone	21	o8e
	dict set reg2tone	20	o8f
	dict set reg2tone	19	o8f+
	dict set reg2tone	18	o8g
	dict set reg2tone	17	o8g+
	dict set reg2tone	16	o8a
	dict set reg2tone	15	o8a+
	dict set reg2tone	14	o8b
	dict set reg2tone	0	r

	set key_list [dict keys $reg2tone]
	
	proc get_ftone {reg} {
		if { $reg == 0} { return [expr int(111860.78125)] }
		
		return [expr int(111860.78125/$reg)]
	}
	
	proc get_tone { reg } {
		variable reg2tone
		variable key_list
		set tone ""
		if {$reg == 0} {
			return "r"
		} elseif {[dict exist $reg2tone $reg] } {
			set tone [dict get $reg2tone $reg]
			return [string range $tone 2 end]
		} else {
			set key_stamp 3421
			foreach key $key_list {
				if { $key > $reg } {
					set key_stamp $key
				} else {
					set delta [expr $key_stamp - $reg]
					set tone [format "%s" [dict get $reg2tone $key_stamp]]
					break
				}
			}
		}
		return [string range $tone 2 end]
	}

	proc get_delta { reg } {
		variable reg2tone
		variable key_list
		set delta 0
		if {[dict exist $reg2tone $reg] } {
			return $delta
		} else {
			set key_stamp 3421
			foreach key $key_list {
				if { $key > $reg } {
					set key_stamp $key
				} else {
					#set ftoneKeyStamp [get_ftone $key_stamp]
					#set ftoneKey      [get_ftone $key]
					##set delta [expr $ftoneKey - $ftoneKeyStamp]
					set delta [expr $key_stamp - $reg]
					break
				}
			}
		}
		return $delta
	}
	
	proc get_octave { reg } {
		variable reg2tone
		variable key_list
		set tone ""
		if {$reg==0} {
			return 1
		} elseif {[dict exist $reg2tone $reg] } {
			set tone [dict get $reg2tone $reg]
			return [string range $tone 1 1]
		} else {
			set key_stamp 0
			foreach key $key_list {
				if { $key > $reg } {
					set key_stamp $key
				} else {
					set delta [expr $key_stamp - $reg ]
					set tone [format "%s" [dict get $reg2tone $key_stamp]]
					break
				}
			}
		}
		return [string range $tone 1 1]
	}
	
	proc get_ftone {reg} {
		if { $reg == 0} { return [expr int(111860.78125)] }
		
		return [expr int(111860.78125/$reg)]
	}

	proc get_mml {line} {
		variable mmlTypePrev
		variable mmlFreqPrev
		variable mmlChPrev
		variable mmlVPrev
		variable mmlOctavePrev
		variable mmlTonePrev
		variable mmlDeltaPrev
		variable mmlLPrev
		variable mmlLCntPrev
		variable mmlWtblIndexPrev
		variable mmlEnvBytePrev
		variable mmlEnvIndexPrev
		variable mmlvDiffPrev
				
		set type      [lindex $line 0]
		set f         [lindex $line 1]
		set ch        [lindex $line 2]
		set v         [lindex $line 3]
		set o         [lindex $line 4]
		set t         [lindex $line 5]
		set d         [lindex $line 6]
		set l         [lindex $line 7]
		set lCnt      [lindex $line 8]
		set wIndex    [lindex $line 9]
		set envByte   [lindex $line 10]
		set envIndex  [lindex $line 11]
		set refLCnt      [lindex $line 12]
		set allChRefLCnt [lindex $line 13]
		set vDiff        [lindex $line 14]
		set repeatCnt    [lindex $line 15]
		
		set mml ""
		set volume ""
		if {$t != "r"} {
			#set temp_v $mmlVPrev
			#set abs [expr abs($temp_v - $v)]
			#if {$abs > 3 } {
			#	puts -nonewline $::mml_util::fd "v$v"
			#} else {
			#	if {$v > $temp_v} {
			#		while {$temp_v < $v } {
			#			# Up 1 in octabe
			#			puts -nonewline $::mml_util::fd ")"
			#			set temp_v [expr $temp_v + 1]
			#		}
			#	} elseif {$v < $temp_v} {
			#		while {$temp_v > $v } {
			#			# Up 1 in octabe
			#			puts -nonewline $::mml_util::fd "("
			#			set temp_v [expr $temp_v - 1]
			#		}
			#	}
			#}
			#puts $::mml_util::fd ";vDiff: $vDiff"
			if {$vDiff > 3 || $vDiff < -3} {
				puts -nonewline $::mml_util::fd "v$v"
			} else {
				if {$vDiff < 0 } {
					while {$vDiff != 0 } {
						# Up 1 in volume
						puts -nonewline $::mml_util::fd "("
						set vDiff [expr $vDiff + 1]
					}
				} elseif {$vDiff > 0 } {
					while {$vDiff != 0 } {
						# Down 1 in volume
						puts -nonewline $::mml_util::fd ")"
						set vDiff [expr $vDiff - 1]
					}
				}
			}
			#puts $::mml_util::fd ";o:             $o"
			#puts $::mml_util::fd ";mmlOctavePrev: $mmlOctavePrev"
			set temp_o $mmlOctavePrev
			if {$o > $temp_o} {
				while {$temp_o < $o } {
					# Up 1 in octabe
					puts -nonewline $::mml_util::fd "\>"
					set temp_o [expr $temp_o + 1]
				}
			} elseif {$o < $temp_o} {
				while {$temp_o > $o } {
					# Up 1 in octabe
					puts -nonewline $::mml_util::fd "\<"
					set temp_o [expr $temp_o - 1]
				}
			}
		}
		
		set mml ""
		set body "${t}"
		#if {$d != 0 && $t != "r" } {
		#	set body "${body}\@\\${d}"
		#}
		#if {$envIndex != -1 && $t != "r" } {
		# 	set body "${body}\@[format "e%02d" $envIndex]"
		#}
		set length $l
		while {$length > 0} {
			#if {$length == 1} {
			#	set mml $body
			#	puts "5"
			#	puts -nonewline $::mml_util::fd $mml
			#	set length [expr $length - 1]
			#} 
			if {$length >= 64 } {
				set mml "${body}1"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - 64]
			} elseif {$length >= 32 } {
				set mml "${body}2"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - 32]
			} elseif {$length >= 16 } {
				set mml "${body}4"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - 16]
			} elseif {$length >= 8 } {
				set mml "${body}8"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - 8]
			} elseif {$length >= 4 } {
				set mml "${body}16"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - 4]		
			} elseif {$length >= 2 } {
				set mml "${body}32"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - 2]
			} elseif {$length >= 1 } {
				set mml "${body}"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - 1]	
			} else {
				set mml "\[$body\]$length"
				puts -nonewline $::mml_util::fd $mml
				set length [expr $length - $length]
			}
		}
		#puts $::mml_util::fd "\n;Done: length $l\n"
	}
	
	proc get_mml2 {line} {
		variable mmlTypePrev
		variable mmlFreqPrev
		variable mmlChPrev
		variable mmlVPrev
		variable mmlOctavePrev
		variable mmlTonePrev
		variable mmlDeltaPrev
		variable mmlLPrev
		variable mmlLCntPrev
		variable mmlWtblIndexPrev
		variable mmlEnvBytePrev
		variable mmlEnvIndexPrev
		variable mmlvDiffPrev
				
		set type      [lindex $line 0]
		set f         [lindex $line 1]
		set ch        [lindex $line 2]
		set v         [lindex $line 3]
		set o         [lindex $line 4]
		set t         [lindex $line 5]
		set d         [lindex $line 6]
		set l         [lindex $line 7]
		set lCnt      [lindex $line 8]
		set wIndex    [lindex $line 9]
		set envByte   [lindex $line 10]
		set envIndex  [lindex $line 11]
		set refLCnt      [lindex $line 12]
		set allChRefLCnt [lindex $line 13]
		set vDiff        [lindex $line 14]
		set repeatCnt    [lindex $line 15]
		
		set mml ""
		set volume ""
		set octaveMML ""
		if {$t != "r"} {
			#set temp_v $mmlVPrev
			#set abs [expr abs($temp_v - $v)]
			#if {$abs > 3 } {
			#	puts -nonewline $::mml_util::fd "v$v"
			#} else {
			#	if {$v > $temp_v} {
			#		while {$temp_v < $v } {
			#			# Up 1 in octabe
			#			puts -nonewline $::mml_util::fd ")"
			#			set temp_v [expr $temp_v + 1]
			#		}
			#	} elseif {$v < $temp_v} {
			#		while {$temp_v > $v } {
			#			# Up 1 in octabe
			#			puts -nonewline $::mml_util::fd "("
			#			set temp_v [expr $temp_v - 1]
			#		}
			#	}
			#}
			
			#puts $::mml_util::fd ";o:             $o"
			#puts $::mml_util::fd ";mmlOctavePrev: $mmlOctavePrev"
			set temp_o $mmlOctavePrev
			if {$o > $temp_o} {
				while {$temp_o < $o } {
					# Up 1 in octabe
					#puts -nonewline $::mml_util::fd "\>"
					set octaveMML "${octaveMML}\>"
					set temp_o [expr $temp_o + 1]
				}
			} elseif {$o < $temp_o} {
				while {$temp_o > $o } {
					# Up 1 in octabe
					#puts -nonewline $::mml_util::fd "\<"
					set octaveMML "${octaveMML}\<"
					set temp_o [expr $temp_o - 1]
				}
			}
			
			#puts $::mml_util::fd ";vDiff: $vDiff"
			if {$vDiff > 3 || $vDiff < -3} {
				#puts -nonewline $::mml_util::fd "v$v"
				set mml "${mml}v$v"
			} else {
				if {$vDiff < 0 } {
					while {$vDiff != 0 } {
						# Up 1 in volume
						#puts -nonewline $::mml_util::fd "("
						set mml "${mml}("
						set vDiff [expr $vDiff + 1]
					}
				} elseif {$vDiff > 0 } {
					while {$vDiff != 0 } {
						# Down 1 in volume
						#puts -nonewline $::mml_util::fd ")"
						set mml "${mml})"
						set vDiff [expr $vDiff - 1]
					}
				}
			}

		}
		
		#set mml ""
		set body "${t}"
		#if {$d != 0 && $t != "r" } {
		#	set body "${body}\@\\${d}"
		#}
		#if {$envIndex != -1 && $t != "r" } {
		# 	set body "${body}\@[format "e%02d" $envIndex]"
		#}
		set length $l
		 while {$length > 0} {
		 	#if {$length == 1} {
		 	#	set mml $body
		 	#	puts "5"
		 	#	puts -nonewline $::mml_util::fd $mml
		 	#	set length [expr $length - 1]
		 	#} 
		 	if {$length >= 64 } {
		 		set mml "${mml}${body}1"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 64]
		 	} elseif {$length >= 32 } {
		 		set mml "${mml}${body}2"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 32]
		 	} elseif {$length >= 16 } {
		 		set mml "${mml}${body}4"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 16]
		 	} elseif {$length >= 8 } {
		 		set mml "${mml}${body}8"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 8]
		 	} elseif {$length >= 4 } {
		 		set mml "${mml}${body}16"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 4]		
		 	} elseif {$length >= 2 } {
		 		set mml "${mml}${body}32"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 2]
		 	} elseif {$length >= 1 } {
		 		set mml "${mml}${body}"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 1]	
		 	} else {
		 		set mml "${mml}\[$body\]$length"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - $length]
		 	}
		 }
		
		if {$repeatCnt > 1} {
			set mml "${octaveMML}\[${mml}\]$repeatCnt"
		} else {
			set mml "${octaveMML}${mml}"
		}
		
		puts -nonewline $::mml_util::fd $mml
		#puts $::mml_util::fd "\n;Done: length $l\n"
	}
	
	proc output_mml2 { line } {
		variable begin_flg
		variable refcount_flg
		variable mmlLineBuffer
		
		variable mmlType
		variable mmlFreq
		variable mmlCh
		variable mmlV
		variable mmlOctave
		variable mmlTone
		variable mmlDelta
		variable mmlL
		variable mmlLCnt
		variable mmlWtblIndex
		variable mmlEnvByte
		variable mmlEnvIndex
		
		variable mmlTypePrev
		variable mmlFreqPrev
		variable mmlChPrev
		variable mmlVPrev
		variable mmlOctavePrev
		variable mmlTonePrev
		variable mmlDeltaPrev
		variable mmlLPrev
		variable mmlLCntPrev
		variable mmlWtblIndexPrev
		variable mmlEnvBytePrev
		variable mmlEnvIndexPrev
		
		#Backup previous line 
		set mmlTypePrev           $mmlType
		set mmlFreq               $mmlFreq
		set mmlChPrev             $mmlCh
		set mmlVPrev              $mmlV
		set mmlOctavePrev         $mmlOctave
		set mmlTonePrev           $mmlTone
		set mmlDeltaPrev          $mmlDelta
		set mmlLPrev              $mmlL
		set mmlLCntPrev           $mmlLCnt
		set mmlWtblIndexPrev      $mmlWtblIndex
		set mmlEnvBytePrev        $mmlEnvByte
		set mmlEnvIndexPrev       $mmlEnvIndex
		
		set type      [lindex $line 0]
		set f         [lindex $line 1]
		set ch        [lindex $line 2]
		set v         [lindex $line 3]
		set o         [lindex $line 4]
		set t         [lindex $line 5]
		set d         [lindex $line 6]
		set l         [lindex $line 7]
		set lCnt      [lindex $line 8]
		set wIndex    [lindex $line 9]
		set envByte   [lindex $line 10]
		set envIndex  [lindex $line 11]
		set refLCnt      [lindex $line 12]
		set allChRefLCnt [lindex $line 13]
		set vDiff        [lindex $line 14]
		set repeatCnt    [lindex $line 15]
				
		variable num_mml
		if {$wIndex != $mmlWtblIndexPrev} {
			variable mmlVPrev $v
		}
		
		#puts $::mml_util::fd "; $line"
		if {$type == "f" || $type == "fv" || $type == "fb0" || $type == "fb1"} {
			if {$::mml_util::begin_flg || $wIndex != $mmlWtblIndexPrev} {
				### HACK
				if {$o == 0 } {
					set o 1
				}
				set num_mml 0
				variable mmlOctavePrev $o
				variable mmlVPrev $v
				set mml "\n[expr $ch+4] @$wIndex v${v}o${o}l64"
				puts $::mml_util::fd $mml
				set ::mml_util::begin_flg 0
				set ::mml_util::newline_flg 1
			} 
			
			if {$::mml_util::newline_flg} {
				set ::mml_util::newline_flg 0
				set mml "\n[expr $ch+4] "
				puts -nonewline $::mml_util::fd $mml
			}			
			get_mml2 $line
			incr num_mml
			if {$num_mml > 8 } {
				set num_mml 0
				set ::mml_util::newline_flg 1
			}
		} elseif {$type == "all0" && $::mml_util::begin_flg == 0} {
			variable mmlVPrev $v
			puts $::mml_util::fd "\n; Total length count: ch4-ch5-ch6-ch7: $allChRefLCnt"
			puts $::mml_util::fd ""
			set ::mml_util::begin_flg 1
			set ::mml_util::newline_flg 1
		} 
		
		#Backup previous line 
		set mmlType           $type
		set mmlFreq           $f
		set mmlCh             $ch
		set mmlV              $v
		set mmlOctave         $o
		set mmlTone           $t
		set mmlDelta          $d
		set mmlL              $l
		set mmlLCnt           $lCnt
		set mmlWtblIndex      $wIndex
		set mmlEnvByte        $envByte
		set mmlEnvIndex       $envIndex
	}

	
	
	# ---
	# --- Read atrace file for greating the list of cpuid
	# ---
    proc read_line_from_csv_file {buffer} {
		variable vStamp
		variable next_all0_flg
		# Skip the lines with space only or new line
        if {[regexp {^$} $buffer] > 0} {
            return
        }
		
		# Skip the comment where begin with '#'
        if {[regexp {^(#)+.} $buffer] > 0} {
            #puts $buffer
            return
        }
        
		# Skip the lines with space only or new line
        if {[regexp {^(,)+.$} $buffer] > 0} {
            return
        }
		
		# Remove multiple spaces starts from begning of line.
        set buffer [regsub {^\x20+} $buffer {}]
		
		if {[regexp {^w,} [lindex $buffer 0]] > 0} {
			set tmp [split $buffer ","]
			set type      [lindex $tmp 0]
			set no        [lindex $tmp 1]
			set bytes     [lindex $tmp 2]
			set line [format "\@s%02d = \{%s\}" $no $bytes]
			lappend ::mml_util::waveTableBufferForMML $tmp
			return;
		} elseif {[regexp {^e,} $buffer] > 0} {
			set tmp [split $buffer ","]
			set type      [lindex $tmp 0]
			set no        [lindex $tmp 1]
			set bytes     [lindex $tmp 2]
			set line [format "\@e%02d = \{,,%s\}" $no $bytes]
			lappend ::mml_util::envelopBufferForMML $tmp
			return;
		} else {
			set tmp [split $buffer ","]
			set ch  [lindex $tmp 2]
			lappend ::mml_util::logBuffer($ch) $buffer
		}
			
		incr ::mml_util::line_number
    }
	
    proc file_read_with_callback_per_line { filename callbackname } {
        set line 0
        if [file exists $filename] {
            set f [open $filename r]
            while {[gets $f buffer] >= 0} {
                incr line
                $callbackname $buffer
            }
            close $f
        } else {
            puts "$filename is not found."
        }
    }

	proc output_header {fd tempo title} {
			puts $fd "\;\[name=scc lpf=1\]"
			puts $fd "#opll_mode 1"
			puts $fd "#tempo $tempo"
			puts $fd "#title \{ \"$title\"\}"
			puts $fd "#alloc 4=3000"
			puts $fd "#alloc 5=3000"
			puts $fd "#alloc 6=3000"
			puts $fd "#alloc 7=3000"
			puts $fd ""
	}
	
	proc optimize_mml {} {
		puts  "optimize_mml open the file"
		set filename test.txt
		set file_handle [open ${::mml_util::output_dir}/${filename} "w"]		
		puts $file_handle "optimize_mml"
		
		for {set ch 0} {$ch < $::mml_util::num_of_ch} {incr ch} {
			set lineNo 0
			set first_line_flg 1
			set lineStamp ""
			set typeStamp ""
			set fStamp ""
			set vStamp ""
			set oStamp ""
			set tStamp ""
			set lStamp ""
			set lCntStamp ""
			set lineStamp ""
			set vDiffStamp 0
			set repeatCntStamp 0
			set ::mml_util::begin_flg 1
			foreach line $::mml_util::IntermediateBufferForMML($ch) {
				puts  $file_handle ""
				puts  $file_handle ";line      : $line"
				puts  $file_handle ";lineStamp : $lineStamp"
				puts ";line      : $line"
				puts ";lineStamp : $lineStamp"
				set type      [lindex $line 0]
				set f         [lindex $line 1]
				set ch        [lindex $line 2]
				set v         [lindex $line 3]
				set o         [lindex $line 4]
				set t         [lindex $line 5]
				set d         [lindex $line 6]
				set l         [lindex $line 7]
				set lCnt      [lindex $line 8]
				set wIndex    [lindex $line 9]
				set envByte   [lindex $line 10]
				set envIndex  [lindex $line 11]
				set refLCnt   [lindex $line 12]
				set allChRefLCnt [lindex $line 13]
				set vDiff        [lindex $line 14]
				set repeatCnt    [lindex $line 15]
				puts $file_handle "repeatCnt: $repeatCnt"
				
				if {$type == "all0" } {
					set lineStamp ""
					set typeStamp ""
					set fStamp ""
					set vStamp ""
					set oStamp ""
					set tStamp ""
					set lStamp ""
					#set lCntStamp ""
					set lineStamp ""
					set vDiffStamp 0
					set repeatCntStamp 0
				}
				
				if {$type == "f" || $type == "fv" || $type == "fb0" || $type == "fb1"} {
					puts $file_handle "tStamp($tStamp) - t($t)"
					puts $file_handle "lStamp($lStamp) - l($l)"
					puts $file_handle "vDiffStamp ($vDiffStamp) - vDiff($vDiff)"
					puts $line
					if { $t == $tStamp && $l == $lStamp && $o == $oStamp && $vDiff == $vDiffStamp && $tStamp != "all0" && $tStamp != "wvtbl"} {
						#set lCnt [expr     $lCntStamp + $l]
						#set line [lreplace $line 8 8 $lCnt]
						set repeatCnt [incr repeatCntStamp]
						set line [lreplace $line 15 15 $repeatCnt]
						puts "Original: [lindex $::mml_util::IntermediateBufferForMML2($ch) end]"
						puts "---->new: $line"
						puts $file_handle "Original: [lindex $::mml_util::IntermediateBufferForMML2($ch) end]"
						puts $file_handle "---->new: $line"
						set ::mml_util::IntermediateBufferForMML2($ch) [lreplace $::mml_util::IntermediateBufferForMML2($ch) end end $line]
						puts $file_handle "Replaced: [lindex $::mml_util::IntermediateBufferForMML2($ch) end]"
					} else {
						puts "lappend ::mml_util::IntermediateBufferForMML2($ch) $line"
						lappend ::mml_util::IntermediateBufferForMML2($ch) $line
					}
				} else {
					lappend ::mml_util::IntermediateBufferForMML2($ch) $line
				}
				
				set lineStamp $line
				set typeStamp $type
				set fStamp $f
				set vStamp $v
				set oStamp $o
				set tStamp $t
				set lStamp $l
				set lCntStamp $lCnt
				set vDiffStamp $vDiff
				set repeatCntStamp $repeatCnt
				
				incr lineNo
			}
			puts "$::mml_util::output_dir/$filename"
		}
		close $
		
		puts "output: $::mml_util::output_dir/$filename"

		
		# Open the files
		set output_file_name ${::mml_util::output_name_body}_2.mml
		set ::mml_util::fd [open ${::mml_util::output_dir}/${output_file_name} w]
		
		output_header $::mml_util::fd 225 "Generate from $output_file_name"
		
		foreach line $::mml_util::waveTableBufferForMML {
			set type      [lindex $line 0]
			set no        [lindex $line 1]
			set bytes     [lindex $line 2]
			set line [format "\@s%02d = \{%s\}" $no $bytes]
			puts $::mml_util::fd $line
		}
		#
		#foreach line $::mml_util::envelopBufferForMML {
		#	read_line_from_csv_file $line
		#}
		
		for {set ch 0} {$ch < $::mml_util::num_of_ch} {incr ch} {
			foreach line $::mml_util::IntermediateBufferForMML2($ch) {
				output_mml2 $line
			}
		}
		# Close files
		close $::mml_util::fd
		
	}

	proc get_mml_MGS { line oStamp vStamp} {
		#type,time,ch,f,v,e,bE,wtbI,ticks,l,vDiff,o,oDiff,cnt
			set type  [lindex $line 0]
			set time  [lindex $line 1]
			set ch    [lindex $line 2]
			set f     [lindex $line 3]
			set v     [lindex $line 4]
			set e     [lindex $line 5]
			set be    [lindex $line 6]
			set wtbI  [lindex $line 7]
			set ticks [lindex $line 8]
			set l     [lindex $line 9]
			set lCnt  [lindex $line 10]
			set t     [lindex $line 11]
			set vDiff [lindex $line 12]
			set o     [lindex $line 13]
			set oDiff [lindex $line 14]
			set cnt   [lindex $line 15]
		
		set oMML ""
		set oDiff [expr $o- $oStamp]
		if {$oDiff > 3 || $oDiff < -3} {
			set oMML "o$o"
		} else {
			if {$oDiff < 0 } {
				while {$oDiff != 0 } {
					# Up 1 in octave
					set oMML "${oMML}\<"
					set oDiff [expr $oDiff + 1]
				}
			} elseif {$oDiff > 0 } {
				while {$oDiff != 0 } {
					# Down 1 in volume
					set oMML "${oMML}\>"
					set oDiff [expr $oDiff - 1]
				}
			}
		}
		set mml ""
		if {$cnt == 1 } { set vDiff [expr $v - $vStamp] }
		if {$vDiff > 3 || $vDiff < -3} {
			#puts -nonewline $::mml_util::fd "v$v"
			set mml "${mml}v$v"
		} else {
			if {$vDiff < 0 } {
				while {$vDiff != 0 } {
					# Up 1 in volume
					#puts -nonewline $::mml_util::fd "("
					set mml "${mml}\("
					set vDiff [expr $vDiff + 1]
				}
			} elseif {$vDiff > 0 } {
				while {$vDiff != 0 } {
					# Down 1 in volume
					#puts -nonewline $::mml_util::fd ")"
					set mml "${mml}\)"
					set vDiff [expr $vDiff - 1]
				}
			}
		}
		
		#set t [get_tone $f]
		set body "${t}"
		puts "---> get_mml_MGS: f: $f: t: ${t} l:$l oMML:$oMML postfix: $mml"
		set length $l
		while {$length > 0} {
		 	if {$length >= 64 } {
		 		set mml "${mml}${body}1"
		 		set length [expr $length - 64]
			} elseif {$length >= 48 } {
		 		set mml "${mml}${body}2."
		 		set length [expr $length - 48]
		 	} elseif {$length >= 32 } {
		 		set mml "${mml}${body}2"
		 		set length [expr $length - 32]
		 	} elseif {$length >= 16 } {
		 		set mml "${mml}${body}4"
		 		set length [expr $length - 16]
		 	} elseif {$length >= 12 } {
		 		set mml "${mml}${body}8."
		 		set length [expr $length - 12]
		 	} elseif {$length >= 8 } {
		 		set mml "${mml}${body}8"
		 		set length [expr $length - 8]
		 	} elseif {$length >= 6 } {
		 		set mml "${mml}${body}16."
		 		set length [expr $length - 6]		
		 	} elseif {$length >= 4 } {
		 		set mml "${mml}${body}16"
		 		set length [expr $length - 4]		
		 	} elseif {$length == 3 } {
		 		set mml "${mml}${body}32."
		 		set length [expr $length - 3]
			} elseif {$length == 2 } {
		 		set mml "${mml}${body}32"
		 		set length [expr $length - 2]
		 	} elseif {$length == 1 } {
		 		set mml "${mml}${body}"
		 		#puts -nonewline $::mml_util::fd $mml
		 		set length [expr $length - 1]	
		 	} else {
		 		set mml "${mml}\[$body\]$length"
		 		set length [expr $length - $length]
		    }
		 }

		puts "---> get_mml_MGS: ---> body: $mml"
		if {$cnt > 1} {
			set mml "${oMML}\[${mml}\]$cnt"
		} else {
			set mml "${oMML}${mml}"
		}
		puts "---> get_mml_MGS: ---> mml: $mml"
		return $mml
	}
	
	proc generate_mml {} {
		variable chOffset
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
		variable mmlBuffer1
		variable mmlBuffer1F
		
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set beginFlg 1
			set newLineFlg 0
			set noteCnt 0
			set lineNo 0
			set mml ""
			set lCnt 0
			set ticksCountFlg 0
			set oStamp 0
			set vStamp    0
			set wtbIStamp 0
			foreach line $workBuffer2($ch) {
				#type,time,ch,f,v,e,bE,wtbI,l,vDiff,o,oDiff
				set type  [lindex $line 0]
				set time  [lindex $line 1]
				set ch    [lindex $line 2]
				set f     [lindex $line 3]
				set v     [lindex $line 4]
				set e     [lindex $line 5]
				set be    [lindex $line 6]
				set wtbI  [lindex $line 7]
				set ticks [lindex $line 8]
				set l     [lindex $line 9]
				set lCnt  [lindex $line 10]
				set t     [lindex $line 11]
				set vDiff [lindex $line 12]
				set o     [lindex $line 13]
				set oDiff [lindex $line 14]
				set cnt   [lindex $line 15]
				
				#set lCnt [expr $lCnt + $l]
				set tmp "; $line"
				puts $tmp
				#lappend mmlBuffer1($ch) $tmp
				#set t [get_tone $f]
				set tmp ";-->o:$o t: $t f:$f v:$v l:$l lCnt:$lCnt ticks: $ticks cnt:$cnt"
				#lappend mmlBuffer1($ch) $tmp
				puts $tmp
				if {$l != 0 } {
					if {$l != 0 && ($type == "f" || $type == "v" || $type == "fv" || $type == "fb0" || $type == "fb1")} {
						set ticksCountFlg 1
						if {$beginFlg || $wtbI != $wtbIStamp} {
							if {$mml != ""} {
								lappend mmlBuffer1($ch) $mml
							}
							set mml "\n[expr $ch + $chOffset] @$wtbI v${v}o${o}l64"
							lappend mmlBuffer1($ch) $mml
							set oStamp $o
							set vStamp $v
							puts ";/*--------------------------------"
							puts "; State of pre definition: $mml"
							set beginFlg 0
							set newLineFlg 1
						}

						if {$newLineFlg} {
							set newLineFlg 0
							set mml "[expr $ch+$chOffset] "
						}
						
				
						set note [get_mml_MGS $line $oStamp $vStamp]
						set mml ${mml}${note}					
						incr noteCnt
						
						if {$noteCnt > 8 } {
							lappend mmlBuffer1($ch) $mml
							set mml ""
							set noteCnt 0
							set newLineFlg 1
						}
						
						if {$be == 0} {
							lappend mmlBuffer1($ch) $mml
							set tmp "; Ticks count: $ticks"
							puts $tmp
							lappend mmlBuffer1($ch) $tmp
							set mml ""
							set noteCnt 0
							set newLineFlg 1
							set ticksCountFlg 0
						}
					}
					set oStamp $o
					set vStamp $v
					set wtbIStamp $wtbI
				} else {
					if {$ticksCountFlg && $be == 0 } {
						set tmp "; Ticks count: $ticks"
						puts $tmp
						lappend mmlBuffer1($ch) $tmp
						set ticksCountFlg 0
					}
				}
				
			}
			set tmp ""
			lappend mmlBuffer1($ch) $tmp
		}
	}

	proc optimize_sw_envelope1 {} {
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
				
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set lineNo 0
			set first_line_flg 1
			set lineStamp ""
			set typeStamp ""
			set fStamp ""
			set vStamp ""
			set oStamp ""
			set tStamp ""
			set lStamp ""
			set lCntStamp ""
			set lineStamp ""
			set vDiffStamp 0
			set repeatCntStamp 0
			foreach line $workBuffer1($ch) {
				#type,time,ch,f,v,e,bE,wtbI,l,vDiff,o,oDiff
				set type  [lindex $line 0]
				set time  [lindex $line 1]
				set ch    [lindex $line 2]
				set f     [lindex $line 3]
				set v     [lindex $line 4]
				set e     [lindex $line 5]
				set be    [lindex $line 6]
				set wtbI  [lindex $line 7]
				set ticks [lindex $line 8]
				set l     [lindex $line 9]
				set lCnt  [lindex $line 10]
				set t     [lindex $line 11]
				set vDiff [lindex $line 12]
				set o     [lindex $line 13]
				set oDiff [lindex $line 14]
				set cnt   [lindex $line 15]
				
				if {$type == "f0" && $e == 0} {
					set lineStamp ""
					set typeStamp ""
					set fStamp ""
					set vStamp ""
					set oStamp ""
					set tStamp ""
					set lStamp ""
					#set lCntStamp ""
					set vDiffStamp 0
					set cntStamp 0
				}
				
				if {$l != 0 } {
					if {$type == "f" || $type == "v" ||$type == "fv" || $type == "fb0" || $type == "fb1"} {
						#puts $line
						puts "$f:$fStamp | $l:$lStamp | $o:$oStamp | $vDiff:$vDiffStamp"
						if { $f == $fStamp && $l == $lStamp && $o == $oStamp && $vDiff == $vDiffStamp} {
							#set lCnt [expr     $lCntStamp + $l]
							#set line [lreplace $line 8 8 $lCnt]
							set cnt [incr cntStamp]
							puts "cnt"
							set line [lreplace $line 15 15 $cnt]
							puts "Original: [lindex $workBuffer2($ch) end]"
							puts "---->new: $line"
							set workBuffer2($ch) [lreplace $workBuffer2($ch) end end $line]
							puts  "Replaced: [lindex $workBuffer2($ch) end]"
						} else {
							lappend workBuffer2($ch) $line
						}
					} else {
						lappend workBuffer2($ch) $line
					}
					
					set lineStamp $line
					set typeStamp $type
					set fStamp $f
					set vStamp $v
					set oStamp $o
					set tStamp $t
					set lStamp $l
					set lCntStamp $lCnt
					set vDiffStamp $vDiff
					set cntStamp $cnt
				} else {
					lappend workBuffer2($ch) $line
				}
				incr lineNo
			}
		}
	}
	
	proc print_list {line} {
		set type  [lindex $line 0]
		set time  [lindex $line 1]
		set ch    [lindex $line 2]
		set f     [lindex $line 3]
		set v     [lindex $line 4]
		set e     [lindex $line 5]
		set be    [lindex $line 6]
		set wtbI  [lindex $line 7]
		set ticks [lindex $line 8]
		set l     [lindex $line 9]
		set lCnt  [lindex $line 10]
		set t     [lindex $line 11]
		set vDiff [lindex $line 12]
		set o     [lindex $line 13]
		set oDiff [lindex $line 14]
		set cnt   [lindex $line 15]
		puts "type:$type, time:$time, ch:$ch, f:$f, v:$v, e:$e, be:$be, wtbI:$wtbI, ticks:$ticks, l:$l, lCnt:$lCnt, t:$t, vDiff:$vDiff, o:$o, oDiff:$oDiff, cnt:$cnt"
				
				
	}
	
	proc optimize_sw_envelope2 {} {
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
				
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set lineNo 0
			set first_line_flg 1
			set lineStamp ""
			set typeStamp ""
			set fStamp ""
			set vStamp ""
			set oStamp ""
			set tStamp ""
			set lStamp ""
			set lCntStamp ""
			set lineStamp ""
			set vDiffStamp 0
			set repeatCntStamp 0
			set cntStamp 0
			puts "optimize_sw_envelope2: ch $ch"
			foreach line $workBuffer1($ch) {
				#type,time,ch,f,v,e,bE,wtbI,l,vDiff,o,oDiff
				set type  [lindex $line 0]
				set time  [lindex $line 1]
				set ch    [lindex $line 2]
				set f     [lindex $line 3]
				set v     [lindex $line 4]
				set e     [lindex $line 5]
				set be    [lindex $line 6]
				set wtbI  [lindex $line 7]
				set ticks [lindex $line 8]
				set l     [lindex $line 9]
				set lCnt  [lindex $line 10]
				set t     [lindex $line 11]
				set vDiff [lindex $line 12]
				set o     [lindex $line 13]
				set oDiff [lindex $line 14]
				set cnt   [lindex $line 15]
				
				if {$type == "f0" && $e == 0} {
					set lineStamp ""
					set typeStamp ""
					set fStamp ""
					set vStamp ""
					set oStamp ""
					set tStamp ""
					set lStamp ""
					#set lCntStamp ""
					set vDiffStamp 0
					set cntStamp 0
				}
				
				if {$l != 0 } {
					if {$type == "f" || $type == "v" ||$type == "fv" || $type == "fb0" || $type == "fb1"} {
						#puts $line
						#puts "f: $f:$fStamp | l: $l:$lStamp | o: $o:$oStamp | v: $v:$vStamp"
						if { $f == $fStamp && $l == $lStamp && $o == $oStamp && $cnt == 1} {
							puts -nonewline "check(cnt==1)!:"
							print_list $line
						} elseif {$cntStamp == 1 && $cnt > 1}  {
							puts -nonewline "check(cnt>1)!:"
							print_list $line
						} else {
							print_list $line
							lappend workBuffer2($ch) $line
						}
					} else {
						print_list $line
						lappend workBuffer2($ch) $line
					}
					
					set lineStamp $line
					set typeStamp $type
					set fStamp $f
					set vStamp $v
					set oStamp $o
					set tStamp $t
					set lStamp $l
					set lCntStamp $lCnt
					set vDiffStamp $vDiff
					set cntStamp $cnt
				} else {
					lappend workBuffer2($ch) $line
				}
				incr lineNo
			}
		}
	}
	
	proc get_ticks { time_s } {
		variable l64
		set ticks [expr int ($time_s * 60)]
		
		# ROUNDUP by demical point 1
		#set ticks [expr int($ticks)]
		
		#if {[expr $time_s - $ticks] > 0 } {
		#	incr ticks
		#}
		return [expr int($ticks)]
	}

	proc get_normalize { length_int } {
		
		if {$length_int > 65 } {
			set length_int [expr int($length_int / 8) * 8 ]
		} elseif {$length_int == 65 || $length_int ==63 } {
			set length_int 64
		} elseif {$length_int == 49 || $length_int == 47 } {
			set length_int 48
		} elseif {$length_int == 33 || $length_int == 31 } {
			set length_int 32
		} elseif {$length_int == 25 || $length_int == 23 } {
			set length_int 24
		} elseif {$length_int == 17 || $length_int == 15 } {
			set length_int 16
		} elseif {$length_int == 13 || $length_int == 11 } {
			set length_int 12
		} elseif {$length_int == 9 || $length_int == 7 } {
			set length_int 8
		} elseif {$length_int == 5 } {
			set length_int 4
		}
		return $length_int
	}
	
	proc get_quantize { ch interval } {
		variable adjustment
		variable l64
		set duration [expr $interval + $adjustment($ch)]
		set length   [expr ($duration / $l64)]
		set length_int [expr int($length)] 
		set length_int [get_normalize $length_int]
		if { $length_int > 0 } {
			set difference [expr ($length - $length_int) * $l64]
			set adjustment($ch) $difference
		} else {
			set adjustment($ch) $duration
		}
		
		return $length_int
	}
	
    proc extrac_to_csv {file_name} {
		variable fd
		variable logBuffer
		variable output_dir
		variable output_name_body
		variable output_file_name
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
		variable mmlBuffer1
		variable mmlBuffer1F
		
		init
		
		# eg. set path "inputs/01_AbovetheHorizon/01_AbovetheHorizon_log.scc.csv"
		# eg. set base [file tail $path]          ;# → 01_AbovetheHorizon_log.scc.csv
		# eg. set root [file rootname $base]      ;# → 01_AbovetheHorizon_log.scc
		# eg. set root [file rootname $root]      ;# → 01_AbovetheHorizon_log

		set path $file_name
		set base [file tail $path] 
		set root [file rootname $base]
		set main [file rootname $root]
		# Set up the file name body for output
        set output_name_body $root
		#set output_name_body [string range $file_name [expr [string last "/" $file_name ] + 1] [expr [string first "." $file_name ] -1]]
		
		# --- Prepare Output folder ---
		set output_dir outputs/${main}
		if {[file exists $output_dir] != 1} {
			file mkdir $output_dir
			puts "$output_dir was created."
		}
	
		# ---
		# --- Read $csv_file for constructing tables
		# ---
		file_read_with_callback_per_line ${file_name} read_line_from_csv_file
        
		array set tempBuffer0 ""
		array set tempBuffer0f ""
		# -------------------------------------------
		# Pass 0 Add Ticks
		# -------------------------------------------
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $logBuffer($ch) {
				#type,time,ch,regF,regV,regE,bitE,wtbI
				set tmp  [split $line ","]
				set type [lindex $tmp 0]
				set time [lindex $tmp 1]
				set ticks [get_ticks $time]
				lappend tmp $ticks
				
				if { $type != "wvtbl"} {
					lappend tempBuffer0($ch) $tmp
				}
			}
		}

		# Dump tempBuffer0($ch) into the file
		set output_file_name ${root}.pass0.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,f,v,e,bE,wtbI,ticks"
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $tempBuffer0($ch) {
				set tmp  [regsub -all " " $line ","]
				puts $fd $tmp
			}
		}
		close $fd
		
		# -------------------------------------------
		# Pass 1 Add l (length)
		# -------------------------------------------
		array set tempBuffer1 ""
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set bufferSize [llength $tempBuffer0($ch)]
			set lCnt 0
			for {set i 0} {$i < $bufferSize} { incr i } {
				set current   [lindex $tempBuffer0($ch) $i]
				set next      [lindex $tempBuffer0($ch) [expr $i + 1]]

				#type,time,ch,regF,regV,regE,bitE,wtbI,ticks
				set time     [lindex $current 1]
				set nextTime [lindex $next 1]
				set interval  [expr $nextTime - $time]
				set l [get_quantize $ch $interval]
				if {$l < 0} {set l 0}
				set line [lappend current $l]
				
				set lCnt [expr $lCnt + $l]
				set line [lappend current $lCnt]
				
				set f [lindex $current 3]
				set t [get_tone $f]
				set line [lappend current $t]
				lappend tempBuffer1($ch) $line
				
				set type [lindex $current 0]
				set e    [lindex $current 5]
				if {$type == "fb0" && $e==0 } {
					#set type "all0"
					#set l    0
					#set line [lreplace $current 0 0 $type]
					#set line [lappend $current $l]
					#lreplace $tempBuffer1($ch) end end $current
					#lappend tempBuffer1($ch) $line
				}
			}
		}
		
		# Dump tempBuffer1($ch) into the file
		set output_file_name ${root}.pass1.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,f,v,e,bE,wtbI,ticks,l,lCnt,t"
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $tempBuffer1($ch) {
				set tmp  [regsub -all " " $line ","]
				puts $fd $tmp
			}
		}
		close $fd

		# -------------------------------------------
		# Pass 2 (Remove if l is 0)
		# -------------------------------------------
		array set tempBuffer2 ""
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach tmp $tempBuffer1($ch) {
				#type,time,ch,regF,regV,regE,bitE,wtbI,ticks,l
				set type  [lindex $tmp 0]
				set l     [lindex $tmp 9]

				if { $l != 0  } {
					lappend tempBuffer2($ch) $tmp
				} else {
					if { $type == "fb0"  } {
						lappend tempBuffer2($ch) $tmp
					}
				}
			}
		}
		
		# Dump tempBuffer2($ch) into the file
		set output_file_name ${root}.pass2.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,f,v,e,bE,wtbI,ticks,l,lCnt,t"
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $tempBuffer2($ch) {
				set tmp  [regsub -all " " $line ","]
				#puts "tmp: $tmp"
				puts $fd $tmp
			}
		}
		close $fd

		#array set tempBuffer3 ""
		#------------------------------------------------------------------------
		# Pass 3 (Add vDiff, o, oDiff,cnt)
		#------------------------------------------------------------------------
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set vStamp 0
			set oStamp 0
			set intervalF 0
			set intervalFStamp 0
			foreach tmp $tempBuffer2($ch) {
				#type,time,ch,regF,regV,regE,bitE,wtbI,ticks,l
				set v     [lindex $tmp 4]
				set vDiff [expr $v - $vStamp]
				lappend tmp $vDiff			
				
				set f [lindex $tmp 3]
				set o [get_octave $f]
				set oDiff [expr $o - $oStamp]
				lappend tmp $o
				lappend tmp $oDiff
				set cnt 1
				lappend tmp $cnt
				
				lappend tempBuffer3($ch) $tmp
				set vStamp $v
				set oStamp $o
			}
		}
		# Dump tempBuffer3($ch) into the file
		set output_file_name ${root}.pass3.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,f,v,e,bE,wtbI,ticks,l,lCnt,t,vDiff,o,oDiff,cnt"
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $tempBuffer3($ch) {
				set tmp  [regsub -all " " $line ","]
				puts $fd $tmp
			}
		}
		close $fd

		# Copy tempBuffer3 to workBuffer2
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $tempBuffer3($ch) {
				lappend workBuffer2($ch) $line
			}
		}
		# generate_mml: Generate mml based on workBuffer2
		generate_mml
		
		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${root}.pass3.mml
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,f,v,e,bE,wtbI,ticks,l,lCnt,t,vDiff,o,oDiff,cnt"
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $mmlBuffer1($ch) {
				puts $fd $line
			}
		}
		close $fd

		#------------------------------------------------------------------------
		# optimize_sw_envelope1
		#------------------------------------------------------------------------		
		# Reset mmlBuffer1,workBuffer1 and workBuffer2
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set mmlBuffer1($ch) ""
			set workBuffer1($ch) ""
			set workBuffer2($ch) ""
		}
		# Copy tempBuffer3 to workBuffer
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $tempBuffer3($ch) {
				lappend workBuffer1($ch) $line
			}
		}
		# optimize_sw_envelope1: Read workBuffer1 and eliminate the line, update the cnt, store it into workBuffer2
		optimize_sw_envelope1
		
		# generate_mml: Read workBuffer2 and generate mml into mmlBuffer1
		generate_mml

		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${output_name_body}.pass3_2.mml
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,f,v,e,bE,wtbI,ticks,l,lCnt,t,vDiff,o,oDiff,cnt"
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $mmlBuffer1($ch) {
				puts $fd $line
			}
		}
		close $fd
		
		#------------------------------------------------------------------------
		# optimize_sw_envelope2
		#------------------------------------------------------------------------
		# Reset mmlBuffer1,workBuffer1 and workBuffer2
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set mmlBuffer1($ch) ""
			set workBuffer1($ch) ""
			#set workBuffer2($ch) ""
		}
		# Copy workBuffer2 to workBuffer1
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $workBuffer2($ch) {
				lappend workBuffer1($ch) $line
			}
		}
		# repeat_count: Read workBuffer1 and eliminate the line, update the cnt, store it into workBuffer2
		optimize_sw_envelope2
		
		# generate_mml: Read workBuffer2 and generate mml into mmlBuffer1
		# generate_mml

		# Dump mmlBuffer1($ch) into the file
		# set output_file_name ${root}.pass3_3.mml
		# set fd [open ${output_dir}/${output_file_name} w]
		# puts $fd "#type,time,ch,f,v,e,bE,wtbI,ticks,l,lCnt,t,vDiff,o,oDiff,cnt"
		# for {set ch 0} {$ch < $num_of_ch} {incr ch} {
		# 	foreach line $mmlBuffer1($ch) {
		# 		puts $fd $line
		# 	}
		# }
		# close $f3
		
    }
}

set csv_file  [lindex $argv 0]
set filename $csv_file 
::mml_util::extrac_to_csv $filename 
