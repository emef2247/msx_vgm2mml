namespace eval scc {

	# ----------------------------
	# TimeStamp
	# ----------------------------
	variable deltaTime  0
	variable globalTime 0
	variable commonTime 0
	variable commonTimeStamp 0
	variable startTime 0

	# ----------------------------
	# Resolution
	# ----------------------------
	variable tick_scale 60
	variable tempo 225
	variable l64 [expr (60.0 / $tempo) / 16]
	variable min_tick_interval 0

	# ----------------------------
	# Channel Information
	# ----------------------------	
	variable ch  0
	variable chStamp  4
	variable num_of_ch 4
	variable offset_of_ch 0

	# ----------------------------
	# Waveform table
	# ----------------------------		
	variable wtbl 0	
	variable wtblByteList ""
	variable wtblDecList ""
	variable wtblBytesList ""
	variable wtblDecCsvList ""

	variable wtbHexData ""
	variable wtbDecCsvData ""
	
	# ----------------------------
	# Register access flags
	# ----------------------------
	variable chAllData ""
	variable ch4Data ""
	variable ch5Data ""
	variable ch6Data ""
	variable ch7Data ""
	variable ch8Data ""

	variable IsWtbNewSet 0
	variable IsWtbLastSet  0
	variable IsF1CtrlSet 0
	variable IsF2CtrlSet 0
	variable IsVCtrlSet 0
	variable IsEnCtrlSet 0
	
	# ----------------------------
	# Waveform registers
	# ----------------------------
	array set wtbNew {}
	array set wtbNew {}

	array set wtbLast {}
	array set wtbLastStamp {}
	
	array set wtbOffset {}
	array set wtbOffsetStamp {}

	array set wtblIndex {}
	array set wtblIndexStamp {}

	
	# ------------------------------
	# Frequency control 1 registers
	# ------------------------------
	array set f1Ctrl {}
	array set f1CtrlStamp {}

	# ------------------------------
	# Frequency control 2 registers
	# ------------------------------
	array set f2Ctrl {}
	array set f2CtrlStamp {}
	
	# ----------------------------
	# Volume control registers
	# ----------------------------
	array set vCtrl {}
	array set vCtrlStamp {}
	
	# ----------------------------
	# Enable control registers
	# ----------------------------
	array set enCtrl {}
	array set enCtrlStamp {}
	
	array set enBit {}
	array set enBitStamp {}

	array set bufferAccessLog {}
	variable bufferAccessTrace 0

	proc init { is_scc_plus } {
		puts "[get_globalTime] [get_time] ([get_ticks $::psg::commonTime]) init $is_scc_plus"
		set ::scc::tempo 75
		set ::scc::globalTime 0
		set ::scc::commonTime 0
		set ::scc::commonTimeStamp 0
		set ::scc::startTime 0
		
		set ::scc::l64 [expr (60.0 / $::scc::tempo) / 16]
		
		set ::scc::ch  0
		set ::scc::chStamp  0
		
		set ::scc::num_of_ch 4
		
		set ::scc::IsWtbNewSet 0
		set ::scc::IsWtbLastSet  0
		set ::scc::IsF1CtrlSet 0
		set ::scc::IsF2CtrlSet 0
		set ::scc::IsVCtrlSet 0
		set ::scc::IsEnCtrlSet 0

		set ::scc::wtbHexData ""
		set ::scc::wtbDecCsvData ""
		
		set ::scc::bufferAccessTrace ""
		set ::scc::header ""

		for {set ch 0} {$ch < $::scc::num_of_ch} {incr ch} {

			# ----------------------------
			# Waveform registers
			# ----------------------------
			set ::scc::wtbNew($ch) 0
			set ::scc::wtbNewStamp($ch) 0

			set ::scc::wtbLast($ch) 0
			set ::scc::wtbLastStamp($ch) 0

			set ::scc::wtbOffset($ch) 0
			set ::scc::wtbOffsetStamp($ch) 0
			
			set ::scc::wtblIndex($ch) 0
			set ::scc::wtblIndexStamp($ch) 0
			
			# -----------------------------
			# Frequency1 control registers
			# -----------------------------
			set ::scc::f1Ctrl($ch) 0
			set ::scc::f1CtrlStamp($ch) 0

			# -----------------------------
			# Frequency2 control registers
			# -----------------------------
			set ::scc::f2Ctrl($ch) 0
			set ::scc::f2CtrlStamp($ch) 0
			
			# ----------------------------
			# Volume control registers
			# ----------------------------
			set ::scc::vCtrl($ch) 0
			set ::scc::vCtrlStamp($ch) 0
	
			# ----------------------------
			# Enable control registers
			# ----------------------------
			set ::scc::enCtrl($ch) 0
			set ::scc::enCtrlStamp($ch) 0
			
			set ::scc::enBit($ch) 0
			set ::scc::enBitStamp($ch) 0
	
			set ::scc::bufferAccessLog($ch) [list]
		}
	}
	
		
	proc new_wavetable {ch data} {
		puts "[get_globalTime] [get_time] ([get_ticks $::psg::commonTime]) new_wavetable"

		update_ch $ch
		
		# Set the new list of ::scc::wtblByteList
		set hex  [format "%02x" $data]
		set ::scc::wtblByteList [list $hex]
		
		set ::scc::wtbOffsetStamp($ch) $::scc::wtbOffset($ch)
		set ::scc::wtbOffset($ch) [expr [llength $::scc::wtblByteList] - 1]
		
		# Set the new list of ::scc::wtblDecList
		set amplitude $data
		if {$amplitude > 127 } { set amplitude [expr 127- $amplitude]}
		set ::scc::wtblDecList [list $amplitude]
	}
	
	proc get_wtblIndex {target_bytes} {
		set index 0

		foreach bytes $::scc::wtblBytesList {
			if {$bytes == $target_bytes} {
				return $index
			}
			incr index
		}
		return $index
	}
	
	proc is_wtbl_bytes_exist {target_bytes} {
		set is_exist 0
		
		foreach bytes $::scc::wtblBytesList {
			if {$bytes == $target_bytes} {
				set is_exist 1
				return $is_exist
			}
		}
		return $is_exist
	}
	
	proc append_wavetable {ch data} {
		puts "[get_globalTime] [get_time] ([get_ticks $::psg::commonTime]) append_wavetable"

		#puts "append_wavetable : time_s: $time_s ch:$ch startTime: $::scc::startTime commonTime: $::scc::commonTime "

		update_ch $ch
		set hex  [format "%02x" $data]
		lappend ::scc::wtblByteList $hex
		
		set amplitude $data
		if {$amplitude > 127 } { set amplitude [expr 127- $amplitude]}
		lappend ::scc::wtblDecList $amplitude
		
		set ::scc::wtbOffsetStamp($ch) $::scc::wtbOffset($ch)
		set ::scc::wtbOffset($ch) [expr [llength $::scc::wtblByteList] - 1]
		
		if { [llength $::scc::wtblByteList] == 32 } {
			set ::scc::iswtbet true
			set wtbl_bytes ""
			foreach byte $::scc::wtblByteList {
				set wtbl_bytes ${wtbl_bytes}${byte}
			}
			set ::scc::wtbl $wtbl_bytes
			
			if {![is_wtbl_bytes_exist $wtbl_bytes]} {
				lappend ::scc::wtblBytesList $wtbl_bytes
				append ::scc::wtbHexData "\n$wtbl_bytes"
				
				set wtbl_dec_csv ""
				foreach dec $::scc::wtblDecList {
					if {$wtbl_dec_csv == "" } {
						set wtbl_dec_csv $dec
					} else {
						set wtbl_dec_csv ${wtbl_dec_csv},${dec}
					}
				}
				lappend ::scc::wtblDecCsvList $wtbl_dec_csv
				append ::scc::wtbDecCsvData "\n$wtbl_dec_csv"
			}
			
			
			set ::scc::wtblIndex($ch) [get_wtblIndex $wtbl_bytes]
		}
	}
	
	proc update_ch {ch} {
		set ::scc::chStamp $::scc::ch
		set ::scc::ch $ch
	}
	
	proc update_time {time_s} {
		puts "[get_globalTime] [get_time] ([get_ticks $::psg::commonTime]) update_time $time_s"
		set ::scc::globalTime $time_s
		
		if {$::scc::startTime == 0} {
			set ::scc::startTime $time_s
		}
		
		# Update ::scc::commonTime
		set ::scc::commonTimeStamp $::scc::commonTime
		set ::scc::commonTime [expr $time_s - $::scc::startTime]
		
		set ::scc::deltaTime [expr $::scc::commonTime - $::scc::commonTimeStamp]
	}
	
	proc get_deltaTime {} {
		return $::scc::deltaTime
	}
	
	proc get_globalTime {} {
		return $::scc::globalTime
	}
	
	proc get_time {} {
		return $::scc::commonTime
	}
	
	proc get_ticks { time_s } {
		variable l64
		puts "get_ticks time_s=$time_s"
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
	
	
	proc write_scc {time_s wp_last_address  wp_last_value } {
		puts "[get_globalTime] [get_time] ([get_ticks $::psg::commonTime]) write_scc [format 0x%x $wp_last_address] [format 0x%x $wp_last_value]"

		set ::scc::ch all

		if {$wp_last_address == 0x9800} {
			::scc::new_wavetable 0 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 0
			::scc::new_wavetable  0 $wp_last_value
		}
		if {$wp_last_address == 0x9820} {
			::scc::new_wavetable 1 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 1
			::scc::new_wavetable  1 $wp_last_value
		}
		if {$wp_last_address == 0x9840} {
			::scc::new_wavetable 2 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 2
			::scc::new_wavetable  2 $wp_last_value
		}
		if {$wp_last_address == 0x9860} {
			::scc::new_wavetable 3 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 3
			::scc::new_wavetable  3 $wp_last_value
		}
		if {0x9800 < $wp_last_address && $wp_last_address < 0x9820} {
			::scc::append_wavetable 0 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 0
		} elseif {0x9820 < $wp_last_address && $wp_last_address < 0x9840} {
			::scc::append_wavetable 1 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 1
		} elseif {0x9840 < $wp_last_address && $wp_last_address < 0x9860} {
			::scc::append_wavetable 2 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 2
		} elseif {0x9860 < $wp_last_address && $wp_last_address < 0x9880} {
			::scc::append_wavetable 3 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 3
		}
		
		if {$wp_last_address == 0x9880} {
			#::scc::update_freqency_channel1 0 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 0
		}
		if {$wp_last_address == 0x9881} {
			#::scc::update_freqency_channel2 0 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 0
		}
		
		if {$wp_last_address == 0x9882} {
			#::scc::update_freqency_channel1 1 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 1
		}
		if {$wp_last_address == 0x9883} {
			#::scc::update_freqency_channel2 1 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 1
		}
		
		if {$wp_last_address == 0x9884} {
			#::scc::update_freqency_channel1 2 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 2
		}
		if {$wp_last_address == 0x9885} {
			#set ::scc::update_freqency_channel2 2 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 2
		}
		if {$wp_last_address == 0x9886} {
			#::scc::update_freqency_channel1 3 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 3
		}
		if {$wp_last_address == 0x9887} {
			#::scc::update_freqency_channel2 3 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 3
		}
		if {$wp_last_address == 0x988a} {
			#::scc::update_volume 0 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 0
		}
		if {$wp_last_address == 0x988b} {
			#::scc::update_volume 1 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 1
		}
		if {$wp_last_address == 0x988c} {
			#::scc::update_volume 2 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 2
		}
		if {$wp_last_address == 0x988d} {
			#::scc::update_volume 3 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 3
		}
		if {$wp_last_address == 0x988f} {
			#::scc::update_enable $wp_last_value
			set ::scc::IsEnCtrlSet 1;set ::scc::ch all 
		}
	
		::scc::update_time $time_s
		::scc::update_registers $::scc::ch $wp_last_value
	}


	proc write_scc_plus {time_s wp_last_address  wp_last_value } {
		puts "[get_globalTime] [get_time] ([get_ticks $::psg::commonTime]) write_scc_plus"

		set ::scc::ch all

		if {$wp_last_address == 0xb800} {
			::scc::new_wavetable 0 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 0
			
		}
		if {$wp_last_address == 0xb820} {
			::scc::new_wavetable 1 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 1
		}
		if {$wp_last_address == 0xb840} {
			::scc::new_wavetable 2 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 2
		}
		if {$wp_last_address == 0xb860} {
			::scc::new_wavetable 3 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 3
		}
		if {$wp_last_address == 0xb880} {
			::scc::new_wavetable 3 $wp_last_value
			set ::scc::IsWtbNewSet 1;set ::scc::ch 4
		}
		if {0xb800 < $wp_last_address && $wp_last_address < 0xb820} {
			::scc::append_wavetable 0 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 0
		} elseif {0xb820 < $wp_last_address && $wp_last_address < 0xb840} {
			::scc::append_wavetable 1 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 1
		} elseif {0xb840 < $wp_last_address && $wp_last_address < 0xb860} {
			::scc::append_wavetable 2 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 2
		} elseif {0xb860 < $wp_last_address && $wp_last_address < 0xb880} {
			::scc::append_wavetable 3 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 3
		} elseif {0xb880 < $wp_last_address && $wp_last_address < 0xb8a0} {
			::scc::append_wavetable 3 $wp_last_value
			set ::scc::IsWtbLastSet 1;set ::scc::ch 4
		}
		
		if {$wp_last_address == 0xb880} {
			#::scc::update_freqency_channel1 0 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 0
		}
		if {$wp_last_address == 0xb881} {
			#::scc::update_freqency_channel2 0 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 0
		}
		
		if {$wp_last_address == 0xb882} {
			#::scc::update_freqency_channel1 1 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 1
		}
		if {$wp_last_address == 0xb883} {
			#::scc::update_freqency_channel2 1 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 1
		}
		
		if {$wp_last_address == 0xb884} {
			#::scc::update_freqency_channel1 2 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 2
		}
		if {$wp_last_address == 0xb885} {
			#set ::scc::update_freqency_channel2 2 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 2
		}
		if {$wp_last_address == 0xb886} {
			#::scc::update_freqency_channel1 3 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 3
		}
		if {$wp_last_address == 0xb887} {
			#::scc::update_freqency_channel2 3 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 3
		}
		if {$wp_last_address == 0xb886} {
			#::scc::update_freqency_channel1 3 $wp_last_value
			set ::scc::IsF1CtrlSet 1;set ::scc::ch 4
		}
		if {$wp_last_address == 0xb887} {
			#::scc::update_freqency_channel2 3 $wp_last_value
			set ::scc::IsF2CtrlSet 1;set ::scc::ch 4
		}
		if {$wp_last_address == 0xb88a} {
			#::scc::update_volume 0 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 0
		}
		if {$wp_last_address == 0xb88b} {
			#::scc::update_volume 1 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 1
		}
		if {$wp_last_address == 0xb88c} {
			#::scc::update_volume 2 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 2
		}
		if {$wp_last_address == 0xb8ad} {
			#::scc::update_volume 3 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 3
		}
		if {$wp_last_address == 0xb8ae} {
			#::scc::update_volume 3 $wp_last_value
			set ::scc::IsVCtrlSet 1;set ::scc::ch 4
		}
		if {$wp_last_address == 0xb8af} {
			#::scc::update_enable $wp_last_value
			set ::scc::IsEnCtrlSet 1;set ::scc::ch all 
		}
	
		::scc::update_time $time_s
		::scc::update_registers $::scc::ch $wp_last_value
	}

	proc get_scc_enable_bit {index regValue } {
		set enableBit 0
		set chValue [expr $index + 1]
		if {[expr $regValue & $chValue]== $chValue} { 
			set enableBit 1 
		} else {
			set enableBit 0
		}
		return $enableBit
	}

	proc update_registers { index regValue } {
		puts "[get_globalTime] [get_time] ([get_ticks $::psg::commonTime]) update_registers $index $regValue"

		set type unkown
		
		if {$index == "all" } {
			for {set ch 0} {$ch < $::scc::num_of_ch} {incr ch} {
				if {$::scc::IsEnCtrlSet} {
					set type enCtrl
					set ::scc::enCtrlStamp($ch) $::scc::enCtrl($ch)
					set ::scc::enCtrl($ch) $regValue
					
					set enBit [get_scc_enable_bit $ch $regValue]
					if {$enBit != $::scc::enBit($ch) } {
						set ::scc::enBitStamp($ch) $::scc::enBit($ch)
						set ::scc::enBit($ch) $enBit
						set type enBit
						
						access_log_in_csv $ch $type
					}
				}
			}
		} else {
			set ch $index
			if {$::scc::IsWtbNewSet} {
				set type wtbNew
				set ::scc::wtbLastStamp($ch) $::scc::wtbLast($ch)
				set ::scc::wtbLast($ch) $regValue
				
				access_log_in_csv $ch $type
			}
		
			if {$::scc::IsWtbLastSet} {
				set type wtbLast
				set ::scc::wtbLastStamp($ch) $::scc::wtbLast($ch)
				set ::scc::wtbLast($ch) $regValue
				
				access_log_in_csv $ch $type
			}
			if {$::scc::IsF1CtrlSet} {
				set type f1Ctrl
				set ::scc::f1CtrlStamp($ch) $::scc::f1Ctrl($ch)
				set ::scc::f1Ctrl($ch) $regValue
				
				access_log_in_csv $ch $type
			}
			if {$::scc::IsF2CtrlSet} {
				set type f2Ctrl
				set ::scc::f2CtrlStamp($ch) $::scc::f2Ctrl($ch)
				set ::scc::f2Ctrl($ch) $regValue
				
				access_log_in_csv $ch $type
			}
			if {$::scc::IsVCtrlSet} {
				set type vCtrl
				set ::scc::vCtrlStamp($ch) $::scc::vCtrl($ch)
				set ::scc::vCtrl($ch) $regValue
				
				access_log_in_csv $ch $type
			}
		}

		# Clear all flags
		set ::scc::IsEnCtrlSet 0
		set ::scc::IsWtbNewSet 0
		set ::scc::IsWtbLastSet 0
		set ::scc::IsF1CtrlSet 0 
		set ::scc::IsF2CtrlSet 0
		set ::scc::IsVCtrlSet 0
	}

	proc access_log_in_csv {ch type} {
	
		set f1Ctrl $::scc::f1Ctrl($ch)
		set f2Ctrl $::scc::f2Ctrl($ch)
		set vCtrl  $::scc::vCtrl($ch)
		set enCtrl $::scc::enCtrl($ch)
		set wtbLast $::scc::wtbLast($ch)
		set wtbOffset $::scc::wtbOffset($ch)
		set enBit $::scc::enBit($ch)
		set wtblIndex $::scc::wtblIndex($ch)

		set time $::scc::commonTime
		set ticks [get_ticks $time]
		set line "$type,$time,$ch,$ticks,,,,,,,,,$enBit,,,,,,,,,,$wtbOffset,$wtbLast,$wtblIndex,$f1Ctrl,$f2Ctrl,$vCtrl,$enCtrl"

		lappend ::scc::bufferAccessLog($ch) $line
		lappend ::scc::bufferAccessTrace $line
	}
	
	proc output_csv {directory file_name} {
		set log_csv_file_name [format %s%s [file rootname $file_name] "_log.scc.csv"]
		set log_csv_file_handle [open $log_csv_file_name "w"]
	
		set header "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,cnt,envlp,envlpIndex,nE,nF,offset,data,wtblIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl"
		puts $log_csv_file_handle $header
		for {set ch 0} {$ch < $::scc::num_of_ch} {incr ch} {			
			foreach line $::scc::bufferAccessLog($ch) {
				puts $log_csv_file_handle $line
			}
			puts $log_csv_file_handle ""
		}
		close $log_csv_file_handle
		puts "directory: $directory  file_name: $log_csv_file_name"
		puts "::scc_util::extrac_to_csv $directory  $log_csv_file_name"
				
		set trace_csv_file_name  [format %s%s [file rootname $file_name] "_trace.scc.csv"]
		set trace_csv_file_handle [open $trace_csv_file_name "w"]
	
		set header "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,cnt,envlpIndex,nE,nF,offset,data,wtblIndex,f1Ctrl,f2Ctrl,vCtrl,enCtrl"
		puts $trace_csv_file_handle $header
		foreach line $::scc::bufferAccessTrace {
			puts $trace_csv_file_handle $line
		}
		close $trace_csv_file_handle
		
		set mml_csv_file_name [format %s%s [file rootname $file_name] "_mml_csv.csv"]
		set mml_csv_file_handle [open $mml_csv_file_name "w"]
		
		
		set wtb_hex_file_name [format %s%s [file rootname $file_name] "_wtb_hex.csv"]
		set wtb_hex_file_handle [open $wtb_hex_file_name "w"]
		fconfigure $wtb_hex_file_handle -translation auto
		puts $wtb_hex_file_handle $::scc::wtbHexData
		close $wtb_hex_file_handle
		set stop_message "wrote data to $wtb_hex_file_name."
		
		set wtb_dec_csv_file_name [format %s%s [file rootname $file_name] "_wtb_dec_csv.csv"]
		set wtb_dec_csv_file_handle [open $wtb_dec_csv_file_name "w"]
		fconfigure $wtb_dec_csv_file_handle -translation auto
		puts $wtb_dec_csv_file_handle $::scc::wtbDecCsvData
		close $wtb_dec_csv_file_handle
		set stop_message "wrote data to $wtb_dec_csv_file_name."
		
		
		puts "directory: $directory  file_name: $trace_csv_file_name"
		puts "::scc_util::extrac_to_csv $directory  $trace_csv_file_name"
	}
}
