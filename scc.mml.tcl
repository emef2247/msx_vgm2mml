namespace eval mml_scc {
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
	set fileNameBody ""
	
	# --- misc variables ---
	set next_all0_flg     0
	set start_to_read_flg 0
	set begin_flg 0
	set refcount_flg 0
	set line_number 0
	set last_buffer ""
	# ----------------------------
	# Waveform table
	# ----------------------------	
	variable wtb 0	
	variable wtbByteList ""
	variable wtbDecList ""
	variable wtbBytesList ""
	variable wtbDecCsvList ""
	
	variable wtbHexData ""
	variable wtbDecCsvData ""
	
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
	
	variable envlpList ""
	set timbreList ""
	
	variable num_of_ch 4
	variable l64 0
	variable chOffset 4
	set      chList ""
	
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
	variable mmlwtbIndex 0
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
	variable mmlwtbIndexPrev 0
	variable mmlEnvBytePrev 0
	variable mmlEnvIndexPrev 0
	variable mmlvDiffPrev 0
	
	variable refLCntStamp 0
	

		
	# --- Table Definition ---
	

	
	# --- File Handle Descriptor ---
	set fd 0

	proc init {} {
		variable chOffset 4
		variable chList ""
		variable tempo 75
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
		variable mmlwtbIndex 0
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
		variable mmlwtbIndexPrev 0
		variable mmlEnvBytePrev 0
		variable mmlEnvIndexPrev 0
		
		for {set ch 0} {$ch < $::mml_scc::num_of_ch} {incr ch} {
			set ::mml_scc::adjustment($ch) 0
			set ::mml_scc::logBuffer($ch) ""
		 	set ::mml_scc::workBuffer1($ch) ""
		 	set ::mml_scc::workBuffer2($ch) ""
		 	set ::mml_scc::mmlBuffer1($ch) ""
		 	set ::mml_scc::mmlBuffer1F($ch) ""
			set ::mml_scc::tempBuffer0T($ch) ""
	
			set ::mml_scc::IntermediateBufferForMML($ch) ""
			set ::mml_scc::IntermediateBufferForMML2($ch) ""
		}
	
		set ::mml_scc::waveTableBufferForMML [list]
		set ::mml_scc::envelopBufferForMML [list]
		set ::mml_scc::headerBufferForMML [list]
	
	}
	
	proc get_enable {  line } {
		#-----------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
		#------------------------------------------------------------------------------------------------------------------------------------------
		set en [lindex $line 12]
		
		return $en
	}
	
	proc get_frequency_from_line { line } {
		#-----------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
		#------------------------------------------------------------------------------------------------------------------------------------------
		set f1 [lindex $line 24]
		set f2 [lindex $line 25]
		set f [expr $f1 + (256*$f2)]
		
		return $f
	}
	
	proc get_volume {  line } {
		#-----------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
		#-----------------------------------------------------------------------------------------------------------------------------------------
		set vCtrl    [lindex $line 26]
		set v [expr $vCtrl & 0xf ]
		return $v
	}
	
	proc get_wtbIndex_from_line {  line } {
		#-----------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
		#-----------------------------------------------------------------------------------------------------------------------------------------
		set wtbIndex 0
		set wtbIndex [lindex $line 23]  

		return $wtbIndex
	}
	
	proc is_timbre_exist { voice } {
		variable timbreList
		
		set isExist 0
		
		foreach timbre $timbreList {
			if {$voice == $timbre} {
				set isExist 1
				return $isExist
			}
		}
		return $isExist
	}
	
	proc get_wtbIndex { voice } {
		variable timbreList
		
		set index 0
		
		foreach timbre $timbreList {
			if {$voice == $timbre} {
				set index 1
				return $index
			}
			incr index
		}
		return -1
	}
	
	proc create_waveform_table { line } {
	
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
		
		if {$buffer == "" } {
			return
		}
		
		# Remove multiple spaces starts from begning of line.
        set buffer [regsub {^\x20+} $buffer {}]
		
		# file header: 
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
		set tmp [split $buffer ","]
		set ch  [lindex $tmp 2]
		
		if { [is_ch_exist $ch] == 0} {
			lappend ::mml_scc::chList $ch
		}
		lappend ::mml_scc::logBuffer($ch) $buffer
			
		incr ::mml_scc::line_number
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
	

	proc get_envlpIndex {target} {
		set index 0

		foreach envlp $::mml_scc::envlpList {
			if {$target == $envlp} {
				return $index
			}
			incr index
		}
		return -1
	}
	
	proc is_envlp_exist {target} {
		set isExist 0
				
		foreach envlp $::mml_scc::envlpList {
			if {[string equal $target $envlp]} {
				set isExist 1
				return $isExist
			}
		}
		return $isExist
	}
	
	proc add_envlp {target } {
		if {[is_envlp_exist $target]} {
			return [get_envlpIndex $target]
		} else {
			lappend ::mml_scc::envlpList $target
			set length [llength $::mml_scc::envlpList]
			return [expr $length -1]
		}
	}
	
	proc init_envlp { } {
		set first_envlp "F"
		set index [add_envlp $first_envlp]
	}
	
	
	proc get_wtbIndex {target_bytes} {
		set index 0

		foreach bytes $::mml_scc::wtbBytesList {
			if {$bytes == $target_bytes} {
				return $index
			}
			incr index
		}
		return $index
	}
	
	proc is_wtb_bytes_exist {target_bytes} {
		set is_exist 0
		
		foreach bytes $::mml_scc::wtbBytesList {
			if {$bytes == $target_bytes} {
				set is_exist 1
				return $is_exist
			}
		}
		return $is_exist
	}

	proc new_wavetable {ch data} {
		# Initialize ::mml_scc::wtbByteList
		set value $data
		set hex  [format "%02x" $value]
		set ::mml_scc::wtbByteList ""
		set ::mml_scc::wtbDecList ""

		lappend ::mml_scc::wtbByteList $hex
		lappend ::mml_scc::wtbDecList $value
			
		for {set i 1} {$i < 32} { incr i} {
			set value 0
			set hex  [format "%02x" $value]
			lappend ::mml_scc::wtbByteList $hex
			lappend ::mml_scc::wtbDecList $value
		}
		puts "new_wavetable: ch:$ch $data $::mml_scc::wtbByteList"
	}
	
	proc append_wavetable {ch offset data} {
		# Update the list of written byte in dex
		set hex  [format "%02x" $data]
		set ::mml_scc::wtbByteList [lreplace $::mml_scc::wtbByteList $offset $offset $hex]
		puts "append_wavetable: $ch $offset $data $::mml_scc::wtbByteList"
		
		# Update the list of 2bytes integer (short)
		set amplitude $data
		if {$amplitude > 127 } { 
			set amplitude [expr 127- $amplitude]
		}
		set ::mml_scc::wtbDecList [lreplace $::mml_scc::wtbDecList $offset $offset $amplitude]
		
		set wtb_bytes ""
		if {$offset == 31} {
			set ::mml_scc::iswtbet true
			foreach byte $::mml_scc::wtbByteList {
				set wtb_bytes ${wtb_bytes}${byte}
			}

			if {![is_wtb_bytes_exist $wtb_bytes]} {
				lappend ::mml_scc::wtbBytesList $wtb_bytes
				
				set wtb_dec_csv ""
				foreach dec $::mml_scc::wtbDecList {
					if {$wtb_dec_csv == "" } {
						set wtb_dec_csv $dec
					} else {
						set wtb_dec_csv ${wtb_dec_csv},${dec}
					}
				}
				lappend ::mml_scc::wtbDecCsvList $wtb_dec_csv
				append ::mml_scc::wtbDecCsvData "\n$wtb_dec_csv"
			}
		} 
		return $wtb_bytes
	}
	
	proc get_volume_diff_in_mml { v vStamp } {
		set mml ""
		set vDiff [expr $vStamp - $v]
		if {$vDiff > 3 || $vDiff < -3} {
			#puts -nonewline $::mml_scc::fd "v$v"
			set mml "v$v"
			return $mml
		} else {
			if {$vDiff < 0 } {
				while {$vDiff != 0 } {
					# Up 1 in volume
					#puts -nonewline $::mml_scc::fd "("
					set mml "${mml}\("
					set vDiff [expr $vDiff + 1]
				}
			} elseif {$vDiff > 0 } {
				while {$vDiff != 0 } {
					# Down 1 in volume
					#puts -nonewline $::mml_scc::fd ")"
					set mml "${mml}\)"
					set vDiff [expr $vDiff - 1]
				}
			}
		}
		return $mml
	}
	
	proc generate_mml {} {
		variable chOffset
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
		variable mmlBuffer1
		variable mmlBuffer1F
		
		foreach ch $::mml_scc::chList {
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
			
			set ch_start "\n\n;ch[expr $ch + $chOffset] start"
			lappend mmlBuffer1($ch) $ch_start
			
			foreach line $workBuffer1($ch) {
				#-----------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
				#-----------------------------------------------------------------------------------------------------------------------------------------
				set type        [lindex $line 0]
				set time        [lindex $line 1]
				set ch          [lindex $line 2]
				set ticks       [lindex $line 3]
				set l           [lindex $line 4]
				set fL          [lindex $line 5]
				set v           [lindex $line 6]
				set fV          [lindex $line 7]
				set f           [lindex $line 8]
				set fF          [lindex $line 9]
				set o           [lindex $line 10]
				set scale       [lindex $line 11]
				set en          [lindex $line 12]
				set fEn         [lindex $line 13]
				set vDiff       [lindex $line 14]
				set vCnt        [lindex $line 15]
				set oDiff       [lindex $line 16]
				set envlp       [lindex $line 17]
				set envlpIndex  [lindex $line 18]
				set nE          [lindex $line 19]
				set nF          [lindex $line 20]
				set offset      [lindex $line 21]
				set data        [lindex $line 22]
				set wtbIndex   [lindex $line 23]
				if {$l > 0 } {		
					set length $l
					set ltmp $l
					while {$length > 0} {
						if { $length > 255} {
							set ltmp 255
						} else {
							set ltmp $length
						}
						#if {$en == 0 } {
						#	set v 0
						#}

						if {$noteCnt == 0} {
							set mml "\n[expr $ch + $chOffset] @${wtbIndex} v${v}"
						}
						
						if {$v != $vStamp && $noteCnt != 0} {
							set mml "${mml} v${v}"
						}
						
						if {$o != $oStamp} {
							set mml "${mml} o${o}"
						}
						
						set mml "${mml} ${scale}%${ltmp} "
						set lCnt [expr $lCnt + $ltmp]
							
						set length [expr $length - $ltmp ]
						if {$length > 0} {
							lappend mmlBuffer1($ch) $mml
							set mml ""
						}
					}
					incr noteCnt
					if {$noteCnt == 8 ||( $type == "enBit" && $en == 0) || $v == 0 } {
						lappend mmlBuffer1($ch) $mml
						set mml ""
						set info "\n;tick count: $lCnt\n"
						lappend mmlBuffer1($ch) $info
						set noteCnt 0
					}
					set wtbIndexStamp $wtbIndex
					set oStamp $o
					set vStamp $v
				}
			}
			if {$mml != "" } {
				lappend mmlBuffer1($ch) $mml
			}
			
			set info "\n;ch[expr $ch + $chOffset] end: tick count: $lCnt\n"
			lappend mmlBuffer1($ch) $info
		}
	}

	proc generate_mml2 {} {
		variable chOffset
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
		variable mmlBuffer1
		variable mmlBuffer1F
		
		foreach ch $::mml_scc::chList {
			set beginFlg 1
			set newLineFlg 0
			set noteCnt 0
			set lineNo 0
			set mml ""
			set lCnt 0
			set ticksCountFlg 0
			set lStamp 0
			set oStamp 0
			set vStamp 0
			set fOStamp 0
			set fVStamp 0
			set envlp ",,"
			set envlpIndex 0
			set envlpIndexStamp 0
			
			set ch_start "\n\n;ch[expr $ch + $chOffset] start"
			lappend mmlBuffer1($ch) $ch_start
			foreach line $workBuffer1($ch) {
				#-----------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
				#-----------------------------------------------------------------------------------------------------------------------------------------
				set type        [lindex $line 0]
				set time        [lindex $line 1]
				set ch          [lindex $line 2]
				set ticks       [lindex $line 3]
				set l           [lindex $line 4]
				set fL          [lindex $line 5]
				set v           [lindex $line 6]
				set fV          [lindex $line 7]
				set f           [lindex $line 8]
				set fF          [lindex $line 9]
				set o           [lindex $line 10]
				set scale       [lindex $line 11]
				set en          [lindex $line 12]
				set fEn         [lindex $line 13]
				set vDiff       [lindex $line 14]
				set vCnt        [lindex $line 15]
				set oDiff       [lindex $line 16]
				set envlp       [lindex $line 17]
				set envlpIndex  [lindex $line 18]
				set nE          [lindex $line 19]
				set nF          [lindex $line 20]
				set offset      [lindex $line 21]
				set data        [lindex $line 22]
				set wtbIndex   [lindex $line 23]
			
				if {$fL > 0  && ($type == "f1Ctrl" || $type == "f2Ctrl")} {
					set length $fL
					set ltmp $fL
					set o [::mml_util::get_octave $fF]
					set scale [::mml_util::get_scale $fF]
					while {$length > 0} {		
						if { $length > 255} {
							set ltmp 255
						} else {
							set ltmp $length
						}
						#if {$en == 0 } {
						#	set v 0
						#}

						if {$noteCnt == 0} {
							set mml "\n[expr $ch + $chOffset] @${wtbIndex} v${fV}"
						}
						
						if {$fV != $fVStamp && $noteCnt != 0} {
							set mml "${mml} v${fV}"
						}
						
						if {$o != $oStamp} {
							set mml "${mml} o${o}"
						}
						
						set mml "${mml} ${scale}%${ltmp}"
						set lCnt [expr $lCnt + $ltmp]
						incr noteCnt

						set length [expr $length - $ltmp ]
					}
					
					if {$noteCnt >= 8 ||( $type == "enBit" && $fEn == 0) } {
						lappend mmlBuffer1($ch) $mml
						set mml ""
						set noteCnt 0
						set info "\n;ch[expr $ch + $chOffset] : tick count: $lCnt\n"
						lappend mmlBuffer1($ch) $info
					}
					set fOStamp $o
					set fVStamp $v
				}
			}
			if {$mml != "" } {
				lappend mmlBuffer1($ch) $mml
			}
			
			# End of the ch 
			set info "\n;ch[expr $ch + $chOffset] end: tick count: $lCnt\n"
			lappend mmlBuffer1($ch) $info
			incr lineNo
		}
	}
	
	proc generate_mml3 {} {
		variable chOffset
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
		variable mmlBuffer1
		variable mmlBuffer1F
		
		init_envlp
		
		foreach ch $::mml_scc::chList {
			set beginFlg 1
			set newLineFlg 0
			set noteCnt 0
			set lineNo 0
			set mml ""
			set lCnt 0
			set vCnt 0
			set vCntStamp 0
			set vLength 0
			set vLengthStamp 0
			set ticksCountFlg 0
			set vStamp 0
			set oStamp 0
			set fVStamp    0
			set envlp ",,"
			set envlpIndex 0
			set envlpIndexStamp 0
			
			set ch_start "\n\n;ch[expr $ch + $chOffset] start"
			lappend mmlBuffer1($ch) $ch_start
			
			foreach line $workBuffer1($ch) {
				#-----------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
				#-----------------------------------------------------------------------------------------------------------------------------------------
				set type        [lindex $line 0]
				set time        [lindex $line 1]
				set ch          [lindex $line 2]
				set ticks       [lindex $line 3]
				set l           [lindex $line 4]
				set fL          [lindex $line 5]
				set v           [lindex $line 6]
				set fV          [lindex $line 7]
				set f           [lindex $line 8]
				set fF          [lindex $line 9]
				set o           [lindex $line 10]
				set scale       [lindex $line 11]
				set en          [lindex $line 12]
				set fEn         [lindex $line 13]
				set vDiff       [lindex $line 14]
				#set vCnt        [lindex $line 15]
				set oDiff       [lindex $line 16]
				set envlp       [lindex $line 17]
				set envlpIndex  [lindex $line 18]
				set nE          [lindex $line 19]
				set nF          [lindex $line 20]
				set offset      [lindex $line 21]
				set data        [lindex $line 22]
				set wtbIndex   [lindex $line 23]
			
				set envStart    0
				set envEnd      0
				set info ""
				set envlpIndexStamp 0
				#set debug_info "\n;$lineNo: $line "
				#lappend mmlBuffer1($ch) $debug_info
				if {$fL > 0  && ($type == "f1Ctrl" || $type == "f2Ctrl")} {
					set length $fL
					set ltmp $fL
					set o [::mml_util::get_octave $fF]
					set scale [::mml_util::get_scale $fF]
					while {$length > 0} {		
						if { $length > 255} {
							set ltmp 255
						} else {
							set ltmp $length
						}
						#if {$en == 0 } {
						#	set v 0
						#}

						if {$noteCnt == 0} {
							set mml "\n[expr $ch + $chOffset] @${wtbIndex} v15 @e[format %02d ${envlpIndex}]"
						}
						
						
						if {$o != $oStamp} {
							set mml "${mml} o${o}"
						}
						
						if {$envlpIndex != $envlpIndexStamp} {
							set mml "${mml} @e[format %02d ${envlpIndex}]"
						}
						
						set mml "${mml} ${scale}%${ltmp}"
						set lCnt [expr $lCnt + $ltmp]
						incr noteCnt

						set length [expr $length - $ltmp ]
					}
					
					if {$noteCnt >= 8 ||( $type == "enBit" && $fEn == 0) } {
						lappend mmlBuffer1($ch) $mml
						set mml ""
						set noteCnt 0
						set info "\n;ch[expr $ch + $chOffset] : tick count: $lCnt\n"
						lappend mmlBuffer1($ch) $info
					}
					
					set fOStamp $o
					set fVStamp $fV
					set vStamp  $v
					set envlpIndexStamp $envlpIndex
				}
			}
			if {$mml != "" } {
				lappend mmlBuffer1($ch) $mml
			}
			
			# End of the ch 
			set info "\n;ch[expr $ch + $chOffset] end: tick count: $lCnt\n"
			lappend mmlBuffer1($ch) $info
			incr lineNo
		}
	}
	
	proc print_list {line} {
				#-----------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
				#-----------------------------------------------------------------------------------------------------------------------------------------
				set type        [lindex $line 0]
				set time        [lindex $line 1]
				set ch          [lindex $line 2]
				set ticks       [lindex $line 3]
				set l           [lindex $line 4]
				set fL          [lindex $line 5]
				set v           [lindex $line 6]
				set fV          [lindex $line 7]
				set f           [lindex $line 8]
				set fF          [lindex $line 9]
				set o           [lindex $line 10]
				set scale       [lindex $line 11]
				set en          [lindex $line 12]
				set fEn         [lindex $line 13]
				set vDiff       [lindex $line 14]
				set vCnt        [lindex $line 15]
				set oDiff       [lindex $line 16]
				set envlp       [lindex $line 17]
				set envlpIndex  [lindex $line 18]
				set nE          [lindex $line 19]
				set nF          [lindex $line 20]
				set offset      [lindex $line 21]
				set data        [lindex $line 22]
				set wtbIndex   [lindex $line 23]
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
		puts "type:$type,time:$time,ch$:ch,ticks:$ticks,l:$l,fL:$fL,v:$v,fV:$fV,f:$f,fF:$fF,o:$o,scale:$scale,en:$en,fEn:$fEn,vDiff:$vDiff,vCnt:$vCnt,oDiff:$oDiff,envlp:$envlp,envlpIndex:$envlpIndex,nE:$nE,nF:$nF,offset:$offset,data:$data,wtbIndex:$wtbIndex"

	}
	
	
	proc get_ticks { time_s } {
		variable l64
		set ticks [expr int(ceil ($time_s * 60))]
		
		# ROUNDUP by demical point 1
		#set ticks [expr int($ticks)]
		
		#if {[expr $time_s - $ticks] > 0 } {
		#	incr ticks
		#}
		if {$ticks == 1} {
			set ticks 0
		}
		return $ticks
	}
	
	proc is_ch_exist { target } {
		set is_exist 0
		foreach ch $::mml_scc::chList {
			if {$target == $ch } { 
				return 1
			}
		}
		return 0
	}
	
    proc extrac_to_csv {directory file_name} {
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
		
		# Set up the file name body for output
        set output_name_body [string range $file_name [expr [string last "/" $file_name ] + 1] [expr [string first "." $file_name ] -1]]
		set ::mml_scc::fileNameBody $output_name_body
		
		# --- Prepare Output folder ---
		set output_dir ${directory}/outputs/${output_name_body}
		if {[file exists $output_dir] != 1} {
			file mkdir $output_dir
			puts "$output_dir was created."
		}
	
		# ---
		# --- Read $csv_file for constructing tables
		# ---
		file_read_with_callback_per_line ${directory}/${file_name} read_line_from_csv_file
        
		array set tempBuffer0 ""
		array set tempBuffer0f ""
		# -------------------------------------------
		# Pass 0 Add Ticks and update wtbIndex
		# -------------------------------------------
		foreach ch $::mml_scc::chList {
			set lineStamp ""
			set lineNo 0
			foreach line $logBuffer($ch) {
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl"
				set tmp  [split $line ","]
				set type [lindex $tmp 0]
				set time [lindex $tmp 1]
				set ch   [lindex $tmp 2]
				set ticks [get_ticks $time]
				#lappend tmp $ticks
				set tmp [lreplace $tmp 3 3 $ticks]
				
				# --------------------------------------------
				# Update wave table
				# --------------------------------------------
				if {$type == "wtbNew" } {
					set wtbLast   [lindex $tmp 22]
					set wtbOffset [lindex $tmp 21]
					::mml_scc::new_wavetable $ch $wtbLast
				}
				
				if {$type == "wtbLast" } {
					set ch [lindex $tmp 2]
					set wtbLast   [lindex $tmp 22]
					set wtbOffset [lindex $tmp 21]
					set wtb_bytes [::mml_scc::append_wavetable $ch $wtbOffset $wtbLast]
					puts "wtbLast: ch:$ch wtbOffset:$wtbOffset wtbLast:$wtbLast wtb_bytes:$wtb_bytes"
					if {$wtbOffset == 31} {
						set wtbIndex [get_wtbIndex $wtb_bytes]
						set tmp [lreplace $tmp 23 23 $wtbIndex]
					}
				}
				
				lappend tempBuffer0($ch) $tmp			
				puts "Pass 0 ch:$ch [format %04d $lineNo]: $tmp"	
				set lineStamp $line
				incr lineNo 
			}
		}

		# Dump tempBuffer0($ch) into the file
		set output_file_name ${::mml_scc::fileNameBody}.scc.pass0.csv
		set fd [open ${output_dir}/${output_file_name} w]
		
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
		puts $fd "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl"
		
		foreach ch $::mml_scc::chList {
			foreach line $tempBuffer0($ch) {
				
				set tmp  [regsub -all " " $line ","]
				puts $fd $tmp
			}
		}
		close $fd
		
		proc copy_registers {src dst } {
			set offset    [lindex $src 21]
			set dst  [lreplace $dst 21 21 $offset]
							
			set data      [lindex $src 22]
			set dst  [lreplace $dst 22 22 $data]
							
			set f1Ctrl    [lindex $src 24]
			set dst  [lreplace $dst 24 24 $f1Ctrl]
							
			set f2Ctrl    [lindex $src 25]
			set dst  [lreplace $dst 25 25 $f2Ctrl]
							
			set vCtrl     [lindex $src 26]
			set dst  [lreplace $dst 26 26 $vCtrl]
							
			set enCtrl    [lindex $src 27]
			set dst  [lreplace $dst 27 27 $enCtrl]
			
			return $dst
		}
		
		proc is_positive_to_negative { vDiff vDiffStamp } {
			if { $vDiffStamp > 0 && $vDiff < 0 } {
				return 1
			} else {
				return 0
			}
		}
		
		proc is_negative_to_positive { vDiff vDiffStamp } {
			if { $vDiffStamp < 0 && $vDiff > 0 } {
				return 1
			} else {
				return 0
			}
		}
	
		# -------------------------------------------
		# Pass 1 Add l (length)
		# -------------------------------------------
		array set tempBuffer1 ""
		foreach ch $::mml_scc::chList {
			set bufferSize [llength $tempBuffer0($ch)]
			set fTicks 0
			set f 0
			set l 0
			set o 1
			set fL -
			set fV -
			set vCnt 0
			set fStamp 0
			set vStamp 0
			set enStamp 0
			set oStamp 1
			set vDiffStamp 0
			set oDiffStamp 0
			set vCntStamp  0
			set fTickStamp 0
			set fLStamp    0
			set fVStamp    0
			set lineStamp ""
			set numOfBuffer [llength $tempBuffer0($ch)]
			for {set index 0 } { $index < $numOfBuffer } { incr index} {
				set line [lindex $tempBuffer0($ch) $index]
				set next [lindex $tempBuffer0($ch) [expr $index + 1]]
				if {$lineStamp != "" } {
					#-----------------------------------------------------------------------------------------------------------------------------------------
					# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
					#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
					#-----------------------------------------------------------------------------------------------------------------------------------------
					set lineTemp $lineStamp
					set currentType [lindex $line 0]
					set nextType    [lindex $next 0]
					set currentL [expr [lindex $line 3] - [lindex $lineStamp 3]]
					set nextL    [expr [lindex $next 3] - [lindex $line 3]]
					if {($currentType == "f1Ctrl" || $currentType =="f2Ctrl") && ($nextType == "f1Ctrl" || $nextType =="f2Ctrl" ) && $nextL == 0} {
						incr index
						set line [lindex $tempBuffer0($ch) $index]
						set next [lindex $tempBuffer0($ch) [expr $index + 1]]
					}
						
					set type     [lindex $lineStamp 0]
					set time     [lindex $lineStamp 1]
					
					#set l 
					set l [expr [lindex $line 3] - [lindex $lineStamp 3]]
					set lineTemp  [lreplace $lineTemp 4 4 $l]

					# fL
					set fTicks [lindex $lineStamp 3]
					if {$type == "f1Ctrl" || $type == "f2Ctrl" ||$type == "enBit"} {
						set fL [expr $fTicks - $fTickStamp]
						set fTickStamp $fTicks
						set lineTemp  [lreplace $lineTemp 5 5 $fL]
					}
					
					# v
					set v [get_volume $lineStamp ]
					set lineTemp [lreplace $lineTemp 6 6 $v]
					
					# fV
					if {$type == "f1Ctrl" || $type == "f2Ctrl" || $type == "enBit"} {
						set fV         $v
						set lineTemp  [lreplace $lineTemp 7 7 $fVStamp]
						set fVStamp    $fV
					}

					#f
					set f [get_frequency_from_line $lineStamp ]
					set lineTemp  [lreplace $lineTemp 8 8 $f]

					#fF
					set fF $fStamp
					set lineTemp  [lreplace $lineTemp 9 9 $fF]
					
					if {$type == "f1Ctrl" || $type == "f2Ctrl"} {
						set fStamp $f
					}
					
					# o
					set o [::mml_util::get_octave $fF]
					set lineTemp [lreplace $lineTemp 10 10 $o]
					
					# Scale
					set scale [::mml_util::get_scale $fF]
					set lineTemp [lreplace $lineTemp 11 11 $scale]

					# en
					set en [get_enable $lineStamp ]
					set lineTemp [lreplace $lineTemp 12 12 $en]

					# fEn
					set fEn $enStamp
					set lineTemp [lreplace $lineTemp 13 13 $fEn]
					if {$type == "f1Ctrl" || $type == "f2Ctrl"} {
						set enStamp $en
					}
					
					# VDiff
					set vDiff [expr [get_volume $line ] - [get_volume $lineStamp ]]
					set lineTemp [lreplace $lineTemp 14 14 $vDiff]
					
					# vCnt
					if {$type == "vCtrl"} {
						incr vCnt
					}
					set lineTemp [lreplace $lineTemp 15 15 $vCnt]
					
					# oDiff
					set nextf [get_frequency_from_line $line ]
					set nextO [::mml_util::get_octave $nextf]
					set oDiff [expr $nextO - $o]
					set lineTemp [lreplace $lineTemp 16 16 $oDiff]
					
					# wtbIndex
					set tim [get_wtbIndex_from_line $lineStamp ]
					set lineTemp [lreplace $lineTemp 23 23 $tim]
					
					# Push lineTemp into tempBuffer1($ch)
					puts "Pass1: tempBuffer1($ch): $lineTemp"
					lappend tempBuffer1($ch) $lineTemp
					
					set vStamp $v
					set oStamp $o
					set vDiffStamp $vDiff
					set oDiffStamp $oDiff
					set vCntStamp  $vCnt
				}
				# fStamp
				if {$type == "f1Ctrl" || $type == "f2Ctrl" } {
					set fStamp $f
					set vCnt 1
				}
				set lineStamp $line
			}
			# Last line
			#-----------------------------------------------------------------------------------------------------------------------------------------
			# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
			#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
			#-----------------------------------------------------------------------------------------------------------------------------------------
			set lineTemp $line
			set type     [lindex $lineStamp 0]
			set time     [lindex $lineStamp 1]
	
			#set l 
			set l [expr [lindex $line 3] - [lindex $lineStamp 3]]
			set lineTemp  [lreplace $lineTemp 4 4 $l]

			# fL
			set fTicks [lindex $lineStamp 3]
			if {$type == "enBit"} {
				set fLStamp $fL
				set fL [expr $fTicks - $fTickStamp]
				set fTickStamp $fTicks
			}
			if {$type == "f1Ctrl" || $type == "f2Ctrl"} {
				set fL [expr $fTicks - $fTickStamp]
				set fTickStamp $fTicks
			}
			set lineTemp  [lreplace $lineTemp 5 5 $fL]

			# v
			set v [get_volume $lineStamp ]
			set lineTemp [lreplace $lineTemp 6 6 $v]
			
			# fV
			if {$type == "f1Ctrl" || $type == "f2Ctrl"} {
				set fV         $v
				set lineTemp  [lreplace $lineTemp 7 7 $fVStamp]
				set fVStamp    $fV
			}
			
			#f
			set f [get_frequency_from_line $lineStamp ]
			set lineTemp  [lreplace $lineTemp 8 8 $f]
			
			#fF
			set fF $fStamp
			set lineTemp  [lreplace $lineTemp 9 9 $fF]
			
			if {$type == "f1Ctrl" || $type == "f2Ctrl"} {
				set fStamp $f
			}
			
			# o
			set o [::mml_util::get_octave $fF]
			set lineTemp [lreplace $lineTemp 10 10 $o]
			
			# Scale
			set scale [::mml_util::get_scale $fF]
			set lineTemp [lreplace $lineTemp 11 11 $scale]

			# en
			set en [get_enable $lineStamp ]
			set lineTemp [lreplace $lineTemp 12 12 $en]

			# fEn
			set fEn $enStamp
			set lineTemp [lreplace $lineTemp 13 13 $fEn]
			if {$type == "f1Ctrl" || $type == "f2Ctrl"} {
				set enStamp $en
			}
					
			# wtbIndex
			set tim [get_wtbIndex_from_line $lineStamp ]
			set lineTemp [lreplace $lineTemp 23 23 $tim]
			
			
			# Push lineTemp into tempBuffer1($ch)
			lappend tempBuffer1($ch) $lineTemp
		}
		
		# Dump tempBuffer1($ch) into the file
		set output_file_name ${output_name_body}.scc.pass1.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl"
		foreach ch $::mml_scc::chList {
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
		foreach ch $::mml_scc::chList {
			set bufferSize [llength $tempBuffer1($ch)]
			set fTicks 0
			set f 0
			set l 0
			set o 1
			set fL -
			set fV -
			set vCnt 0
			set enStamp 0
			set fStamp 0
			set vStamp 0
			set oStamp 1
			set vDiffStamp 0
			set oDiffStamp 0
			set vCntStamp  0
			set fTickStamp 0
			set fLStamp    0
			set fVStamp    0
			set lineStamp ""
			set numOfBuffer [llength $tempBuffer1($ch)]
			for {set index 0 } { $index < $numOfBuffer } { incr index} {
				set line [lindex $tempBuffer1($ch) $index]
				set next [lindex $tempBuffer1($ch) [expr $index + 1]]
				if {$lineStamp != "" } {
					#-----------------------------------------------------------------------------------------------------------------------------------------
					# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
					#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
					#-----------------------------------------------------------------------------------------------------------------------------------------
					set lineTemp $lineStamp
					# Push lineTemp into tempBuffer2($ch)
					
					set type [lindex $lineTemp 0 ]
					if {$type != "wtbNew" && $type != "wtbLast"} {
						puts "Pass2: tempBuffer2($ch): $lineTemp"
						lappend tempBuffer2($ch) $lineTemp
					}
					
					set currentType [lindex $line 0]
					set nextType    [lindex $next 0]
					set currentL [expr [lindex $line 3] - [lindex $lineStamp 3]]
					set nextL    [expr [lindex $next 3] - [lindex $line 3]]
					if {($currentType == "f1Ctrl" || $currentType =="f2Ctrl") && (($nextType == "vCtrl" || $nextType == "enBit" )&& $nextL == 0)} {
						#If the volume of "line" will be ovverritten by the next line of vCtrl, it will be marged to the line.
						# type
						set next [lreplace $next 0 0 $currentType]
					
						# l
						# set l [lindex $line 4]
						# set next  [lreplace $next 4 4 $l]
						# fL
						set fL [lindex $line 5]
						set next  [lreplace $next 5 5 $fL]
					
						# v
						#set v [lindex $next 6]
						#set next [lreplace $next 6 6 $v]
						
						# fV
						set fV [lindex $line 7]
						set next [lreplace $next 7 7 $fV]
						
						#f
						set f [lindex $line 8]
						set next [lreplace $next 8 8 $f]
					
						#fF
						set f [lindex $line 9]
						set next [lreplace $next 9 9 $f]
						
						# o
						set o [lindex $line 10]
						set next [lreplace $next 10 10 $o]
						
						# Scale
						set scale [lindex $line 11]
						set next [lreplace $next 11 11 $scale]
					
						# en
						#set en [lindex $line 12]
						#set next [lreplace $next 12 12 $en]
						
						# fEn
						set fEn [lindex $line 13]
						set next [lreplace $next 13 13 $fEn]
					
						# VDiff
						#set vDiff [lindex $line 14]
						#set next [lreplace $next 14 14 $vDiff]
						
						# vCnt
						set vCnt [lindex $line 15]
						set next [lreplace $next 15 15 $vCnt]
					
						# oDiff
						#set oDiff [lindex $line 16]
						#set next [lreplace $next 16 16 $oDiff]
					
						# wtbIndex
						set tim [lindex $line 23]
						set next [lreplace $next 23 23 $tim]
						
						# Push lineTemp into tempBuffer2($ch)
						puts "Pass2: tempBuffer2($ch): $lineTemp"
						lappend tempBuffer2($ch) $next
					
						incr index
						incr index
						# Delite next line
						#incr index
						#set line [lindex $tempBuffer1($ch) $index]
						#set next [lindex $tempBuffer1($ch) [expr $index + 1]]
						set line [lindex $tempBuffer1($ch) $index]
					}
				}
				set lineStamp $line
			}
			# Last line
			set lineTemp $lineStamp
			# Push lineTemp into tempBuffer2($ch)
			set type [lindex $lineTemp 0 ]
			if {$lineTemp != "" && $type != "wtbNew" && $type != "wtbLast"} {
				puts "Pass2: tempBuffer2($ch): $lineTemp"
				lappend tempBuffer2($ch) $lineTemp
			}
			
			#-----------------------------------------------------------------------------------------------------------------------------------------
			# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
			#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
			#-----------------------------------------------------------------------------------------------------------------------------------------

		}
		# Dump tempBuffer2($ch) into the file
		set output_file_name ${output_name_body}.scc.pass2.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl"
		foreach ch $::mml_scc::chList {
			foreach line $tempBuffer2($ch) {
				set tmp  [regsub -all " " $line ","]
				#puts "tmp: $tmp"
				puts $fd $tmp
			}
		}
		close $fd

		array set tempBuffer3 ""
		#------------------------------------------------------------------------
		# Pass 3 (Add vDiff, o, oDiff,cnt)
		#------------------------------------------------------------------------
		init_envlp
		
		foreach ch $::mml_scc::chList {
			set beginFlg 1
			set newLineFlg 0
			set noteCnt 0
			set lineNo 0
			set mml ""
			set lCnt 0
			set vCnt 0
			set vCntStamp 0
			set vLength 0
			set vLengthStamp 0
			set ticksCountFlg 0
			set ltamp 0
			set vStamp 0
			set oStamp 0
			set vDiffStamp 0
			set fVStamp    0
			set envlp "F"
			set envlpStamp "F"
			set vEnvlp ""
			set vEnvlpStamp ""
			set vEnvlpTemp ""
			set envlpIndex 0
			set envlpIndexStamp 0
			set lineStamp ""
			foreach line $tempBuffer2($ch) {
				#-----------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26    27
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl
				#-----------------------------------------------------------------------------------------------------------------------------------------
				set type        [lindex $line 0]
				set time        [lindex $line 1]
				set ch          [lindex $line 2]
				set ticks       [lindex $line 3]
				set l           [lindex $line 4]
				set fL          [lindex $line 5]
				set v           [lindex $line 6]
				set fV          [lindex $line 7]
				set f           [lindex $line 8]
				set fF          [lindex $line 9]
				set o           [lindex $line 10]
				set scale       [lindex $line 11]
				set en          [lindex $line 12]
				set fEn         [lindex $line 13]
				set vDiff       [lindex $line 14]
				#set vCnt        [lindex $line 15]
				set oDiff       [lindex $line 16]
				#set envlp       [lindex $line 17]
				#set envlpIndex  [lindex $line 18]
				set nE          [lindex $line 19]
				set nF          [lindex $line 20]
				set offset      [lindex $line 21]
				set data        [lindex $line 22]
				set wtbIndex   [lindex $line 23]
			
				set envStart    0
				set envEnd      0
				#set debug_info "\n;$lineNo: $line "
				#lappend mmlBuffer1($ch) $debug_info
				if {$fL > 0  && ($type == "f1Ctrl" || $type == "f2Ctrl")} {
					set fOStamp $o
					set fVStamp $fV
					set vStamp  $v
					
					if {$vCnt > 1} {
						set envlp "${envlp}.${vEnvlp}"
					} else {
						set envlp "F"
					}
					set envlpIndex [add_envlp $envlp]
					set line  [lreplace $line 17 17 $envlp]
					set line  [lreplace $line 18 18 $envlpIndex]

				
					set vCntSample $vCnt
					set vCnt 1

					set vLengthStamp $vLength
					set vLength $l
					set vEnvlp ""
					set vEnvlpStamp ""
					set vEnvlpTemp ""
					set envlpStamp $envlp
					set envlp "[format %X ${v}]"
				}

				if { $type == "vCtrl" || $type == "enBit"} {
					if {$l > 0} {
						incr vCnt
					}
					set vLength [expr $vLength +$l]
					set vStamp $v
					
					
					if {$vCnt > 1 || $l != 0} {
						if {$vEnvlpTemp != ""} {
							if {$vLength > 1} {
								set vEnvlp "${vEnvlpTemp}.[format %X ${v}]=${vLength}"
							} else {
								set vEnvlp "${vEnvlpTemp}.[format %X ${v}]"
							}
						} else {
							if {$vLength > 1} {
								set vEnvlp "[format %X ${v}]=${vLength}"
								} else {
								set vEnvlp "[format %X ${v}]"
							}
						}
					} 
					if { ($vDiff > 0 && [is_negative_to_positive $vDiff $vDiffStamp ]) || ($vDiff < 0 && [is_positive_to_negative $vDiff $vDiffStamp ])} {
						#set vEnvlp "${vEnvlp}.[format %X ${v}]"
						set vEnvlpTemp "${vEnvlp}"
						set vLength $l
					} 
					set line  [lreplace $line 17 17 $vEnvlp]
					
				}
				puts "Pass3: tempBuffer3($ch): $line"
				lappend tempBuffer3($ch) $line
				set envlpStamp $envlp
				set vDiffStamp $vDiff
				incr lineNo
			}
		}
		# Dump tempBuffer3($ch) into the file
		set output_file_name ${output_name_body}.scc.pass3.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl"
		
		foreach ch $::mml_scc::chList {
			foreach line $tempBuffer3($ch) {
				set tmp  [regsub -all " " $line ","]
				puts $fd $tmp
			}
		}
		close $fd

		# Copy tempBuffer3 to workBuffer1
		foreach ch $::mml_scc::chList {
			foreach line $tempBuffer3($ch) {
				lappend workBuffer1($ch) $line
			}
		}
		# generate_mml: Generate mml based on workBuffer2
		generate_mml
		
		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${output_name_body}.scc.pass3.mml
		set fd [open ${output_dir}/${output_file_name} w]
		
		
		puts $fd ";\[name=scc lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"$::mml_scc::fileNameBody\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""
		set index 0
		foreach wtbBytes $::mml_scc::wtbBytesList {
			puts $fd "\@s[format %02d $index] = \{$wtbBytes\}"
			incr index
		}
		puts $fd ""
		foreach ch $::mml_scc::chList {
			foreach line $mmlBuffer1($ch) {
				puts -nonewline $fd $line
			}
		}
		close $fd

		# generate_mml: Read workBuffer2 and generate mml into mmlBuffer1
		array unset  mmlBuffer1
		generate_mml2

		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${output_name_body}.scc.pass3_2.mml
		set fd [open ${output_dir}/${output_file_name} w]
		
		puts $fd ";\[name=scc lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"$::mml_scc::fileNameBody\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""
		set index 0
		foreach wtbBytes $::mml_scc::wtbBytesList {
			puts $fd "\@s[format %02d $index] = \{$wtbBytes\}"
			incr index
		}
		puts $fd ""

		set index 0
		foreach envlp $::mml_scc::envlpList {
			puts $fd "\@e[format %02d $index] = \{,,$envlp\}"
			incr index
		}
		puts $fd ""

		foreach ch $::mml_scc::chList {
			foreach line $mmlBuffer1($ch) {
				puts $fd $line
			}
		}
		close $fd	

		# generate_mml: Read workBuffer2 and generate mml into mmlBuffer1
		array unset  mmlBuffer1
		generate_mml3

		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${output_name_body}.scc.pass3_3.mml
		set fd [open ${output_dir}/${output_file_name} w]
		
		puts $fd ";\[name=scc lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"$::mml_scc::fileNameBody\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""
		set index 0
		foreach wtbBytes $::mml_scc::wtbBytesList {
			puts $fd "\@s[format %02d $index] = \{$wtbBytes\}"
			incr index
		}
		puts $fd ""

		set index 0
		foreach envlp $::mml_scc::envlpList {
			puts $fd "\@e[format %02d $index] = \{,,$envlp\}"
			incr index
		}
		puts $fd ""

		foreach ch $::mml_scc::chList {
			foreach line $mmlBuffer1($ch) {
				puts $fd $line
			}
		}
		close $fd
    }
}


set script_dir [file dirname [file normalize [info script]]]
set directory $script_dir

source $script_dir/mml_utils.tcl

# Get the filename from the first argument
set filename [lindex $argv 0]

::mml_scc::extrac_to_csv $directory $filename


