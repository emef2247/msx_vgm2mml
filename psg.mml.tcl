namespace eval ::mml_psg {
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
	
	set timbreList ""
	
	variable num_of_ch 3
	variable l64 0
	variable chOffset 1
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
		variable chOffset 1
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
		
		for {set ch 0} {$ch < $::mml_psg::num_of_ch} {incr ch} {
			set ::mml_psg::adjustment($ch) 0
			set ::mml_psg::logBuffer($ch) ""
		 	set ::mml_psg::workBuffer1($ch) ""
		 	set ::mml_psg::workBuffer2($ch) ""
		 	set ::mml_psg::mmlBuffer1($ch) ""
		 	set ::mml_psg::mmlBuffer1F($ch) ""
	
			set ::mml_psg::IntermediateBufferForMML($ch) ""
			set ::mml_psg::IntermediateBufferForMML2($ch) ""
		}
	
		set ::mml_psg::waveTableBufferForMML [list]
		set ::mml_psg::envelopBufferForMML [list]
		set ::mml_psg::headerBufferForMML [list]
	
	}
	
	proc is_voise_enabled {  line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set ch     [lindex $line 2]
		set vVCtrl [lindex $line 27]
		set voiceMute [expr $vVCtrl & 0x7]
		 
		set mask 1
		switch $ch {
		0 {set mask 1}
		1 {set mask 2}
		2 {set mask 4}
		}
		
		set isVoiceEnabled 1
		if {[expr $voiceMute & $mask] == $mask } {
			set isVoiceEnabled 0
		} 
		
		return $isVoiceEnabled
	}
	
	proc is_noise_enabled {  line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set ch     [lindex $line 2]
		set vVCtrl [lindex $line 27]
		set noiseMute [expr ($vVCtrl / 8) & 0x7]
		 
		set mask 1
		switch $ch {
		0 {set mask 1}
		1 {set mask 2}
		2 {set mask 4}
		}
		
		set isNoiseEnabled 1
		if {[expr $noiseMute & $mask] == $mask } {
			set isNoiseEnabled 0
		} 
		

		return $isNoiseEnabled
	}
	
	
	proc get_enable {  line } {
		set isNoiseEnabled [is_noise_enabled $line]
		set isVoiseEnabled [is_voise_enabled $line]

		set isAudioOutEnabled 0
		if {$isNoiseEnabled || $isVoiseEnabled} {
			set isAudioOutEnabled 1
		}
		
		return $isAudioOutEnabled
	}
	
	proc get_frequency_from_line { line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set fCtrlA [lindex $line 24]
		set fCtrlB [lindex $line 25]
		puts ""
		set f [expr $fCtrlA + (256*$fCtrlB)]
		return $f
	}
	
	proc get_volume {  line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set aVCtrl    [lindex $line 28]
		set v [expr $aVCtrl & 0xf ]
		return $v
	}
	
	proc get_timbre_index {  line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set timbreIndex 0
		set wNCtrl    [lindex $line 26]  
		set vVCtrl    [lindex $line 27]
		set aVCtrl    [lindex $line 28]
		set envPCtrlL [lindex $line 29]
		set envPCtrlM [lindex $line 30]
		set envShape  [lindex $line 31]
		
		set mode         [expr $vVCtrl/64]
		set noisePeriod  [expr $wNCtrl & 0x1f]
		
		set timbre "$mode-$noisePeriod"
		# set isHwEnvelope [expr $aVCtrl/16]
		# set volume       [expr $aVCtrl & 0xf]
		# 
		# set isNoiseEnabled [IsNoiseEnabled $line]
		# set isVoiseEnabled [IsVoiseEnabled $line]
		# 
		# # Registers 11 and 12 control the envelope period. The value is on 16 bits (0~65535). It is calculated with the following expression:
		# # Value = Fi / (256 x T)
		# # Fi = Internal frequency of PSG (1789772.5 Hz on MSX)
		# # T = Period of the envelope (in μs)
		# set envPeriod [expr ($envPCtrlM * 256) + $envPCtrlL]

		#@e<number> = { Mode,Noise,data...data }
		
		#https://mus.msx.click/index.php?title=MGSDRV_MML_11_JP#.23psg_tune.09.7B_c.E3.81.AE.E9.9F.B3.E7.A8.8B.E3.83.87.E3.83.BC.E3.82.BF.2Cc.23.E3.81.AE.E9.9F.B3.E7.A8.8B.E3.83.87.E3.83.BC.E3.82.BF_...._b.E3.81.AE.E9.9F.B3.E7.A8.8B.E3.83.87.E3.83.BC.E3.82.BF_.7D
		
		return $timbre
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
	
	proc get_timbre_index { voice } {
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
	
	proc get_mode {  line } {
		set mode [lindex $line 11]
		return $mode
	}
	
	proc get_noise_period { line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set wNCtrl [lindex $line 26]
		set noisePeriod  [expr $wNCtrl & 0x1f]
		return $noisePeriod
	}
	
	proc get_hw_envelope_on { line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set aVCtrl [lindex $line 28]
		set hwENvOn [expr $aVCtrl / 16]
		
		return $hwENvOn
	}
	
	proc get_hw_envelope_freqency { line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set envPCtrlL [lindex $line 29]
		set envPCtrlM [lindex $line 30]
		set envPeriod [expr ($envPCtrlM *256) + $envPCtrlL]
		
				
		# T =(256*EP)/fc =(256*EP)/1.7897725 [MHz] =143.03493*EP [μs]
		set envFrequency [expr int(143.03493 * $envPeriod) ]
		
		return $envFrequency
	}
	
	proc get_hw_envelope_shape { line } {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set envShape  [expr [lindex $line 31] & 0xf]
		
		return $envShape
	}
	
	proc create_timbre { line } {
		variable timbreList
		set mode [get_mode $line ]
		set noisePeriod [get_noise_period $line]
		set hwEnvOn     [get_hw_envelope_on $line]
		set hwEnvPeriod [get_hw_envelope_freqency $line]
		set hwEnvShape  [get_hw_envelope_shape $line]
		
		set timbre "${mode},${noisePeriod},${hwEnvOn},${hwEnvPeriod},${hwEnvShape}"
		
		set index [get_timbre_index $timbre]
		if {$index == -1 } {
			lappend timbreList $timbre
			return [get_timbre_index $timbre]
		}
		return $index
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
		
		if {[string trim $buffer] eq ""} {
			puts "改行だけの行を検出しました"
			return
		}
		
		# Remove multiple spaces starts from begning of line.
        set buffer [regsub {^\x20+} $buffer {}]
		
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set tmp [split $buffer ","]
		set ch  [lindex $tmp 2]
		
		if { [is_ch_exist $ch] == 0} {
			lappend ::mml_psg::chList $ch
		}
		lappend ::mml_psg::logBuffer($ch) $buffer
			
		incr ::mml_psg::line_number
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

	proc get_volume_diff_in_mml { v vStamp } {
		set mml ""
		set vDiff [expr $vStamp - $v]
		if {$vDiff > 3 || $vDiff < -3} {
			#puts -nonewline $::mml_psg::fd "v$v"
			set mml "v$v"
			return $mml
		} else {
			if {$vDiff < 0 } {
				while {$vDiff != 0 } {
					# Up 1 in volume
					#puts -nonewline $::mml_psg::fd "("
					set mml "${mml}\("
					set vDiff [expr $vDiff + 1]
				}
			} elseif {$vDiff > 0 } {
				while {$vDiff != 0 } {
					# Down 1 in volume
					#puts -nonewline $::mml_psg::fd ")"
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
		
		foreach ch $::mml_psg::chList {
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
				#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
				#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				set type       [lindex $line 0]
				set time       [lindex $line 1]
				set ch         [lindex $line 2]
				set ticks      [lindex $line 3]
				set l          [lindex $line 4]
				set fL         [lindex $line 5]
				set v          [lindex $line 6]
				set fV         [lindex $line 7]
				set f          [lindex $line 8]
				set fF         [lindex $line 9]
				set o          [lindex $line 10]
				set scale      [lindex $line 11]
				set mode       [lindex $line 12]
				set fMode      [lindex $line 13]
				set vDiff      [lindex $line 14]
				set vCnt       [lindex $line 15]
				set oDiff      [lindex $line 16]
				set envlp      [lindex $line 17]
				set envlpIndex [lindex $line 18]
				set nE         [lindex $line 19]
				set nF         [lindex $line 20]
				set noisePeriod [get_noise_period $line]
				set hwEnvOn     [get_hw_envelope_on $line]
				set hwEnvPeriod [get_hw_envelope_freqency $line]
				set hwEnvShape  [get_hw_envelope_shape $line]

				puts  "noteCnt:$noteCnt mml:$mml mode:$mode"
				if {$l > 0 } {
					set noiseFreq    [get_noise_period $line]
				
					set length $l
					set ltmp $l
					
					if {$noteCnt == 0} {
						switch $mode {
							0 {set v 0;set mml "\n[expr $ch + $chOffset] \/0 v${v}"}
							1 {set mml "\n[expr $ch + $chOffset] \/1 s${hwEnvShape} m${hwEnvPeriod} v${v}"}
							2 {set mml "\n[expr $ch + $chOffset] \/2 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"} 
							3 {set mml "\n[expr $ch + $chOffset] \/3 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"}
						}
						puts "after node noteCnt:$noteCnt mml:$mml"
					}
						
					while {$length > 0} {
						if { $length > 255} {
							set ltmp 255
						} else {
							set ltmp $length
						}
							
						if {($type == "mode" || $type == "fCA" || $type == "fCB" || $type == "aVC" || $type == "wNC" || $type == "vVC" || $type == "ePL" || $type == "evM " || $type == "evS")} {

							if {$mode == 0} {
								set v 0
							}

							if {$v != $vStamp && $noteCnt != 0} {
								set mml "${mml} v${v}"
							}
							
							if {$o != $oStamp} {
								set mml "${mml} o${o}"
							}
							
							set mml "${mml} ${scale}%${ltmp}"
							set lCnt [expr $lCnt + $ltmp]
							
						}
						set length [expr $length - $ltmp ]
						
						if {$length >= 0} {
							lappend mmlBuffer1($ch) $mml
							set mml ""
						}
					}
					
					incr noteCnt
					if {$noteCnt == 8 || $mode == 0 } {
						lappend mmlBuffer1($ch) $mml
						set mml ""
						set info "\n;tick count: $lCnt\n"
						lappend mmlBuffer1($ch) $info
						set noteCnt 0
					}
					set oStamp $o
					set vStamp $v
				}
			}
		}
		set info "\n;ch[expr $ch + $chOffset] end: tick count: $lCnt\n"
		lappend mmlBuffer1($ch) $info
	}

	proc generate_mml2 {} {
		variable chOffset
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
		variable mmlBuffer1
		variable mmlBuffer1F
		
		foreach ch $::mml_psg::chList {
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
				#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
				#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				set type       [lindex $line 0]
				set time       [lindex $line 1]
				set ch         [lindex $line 2]
				set ticks      [lindex $line 3]
				set l          [lindex $line 4]
				set fL         [lindex $line 5]
				set v          [lindex $line 6]
				set fV         [lindex $line 7]
				set f          [lindex $line 8]
				set fF         [lindex $line 9]
				set o          [lindex $line 10]
				set scale      [lindex $line 11]
				set mode       [lindex $line 12]
				set fMode      [lindex $line 13]
				set vDiff      [lindex $line 14]
				set vCnt       [lindex $line 15]
				set oDiff      [lindex $line 16]
				set envlp      [lindex $line 17]
				set envlpIndex [lindex $line 18]
				set nE         [lindex $line 19]
				set nF         [lindex $line 20]
				set noisePeriod [get_noise_period $line]
				set hwEnvOn     [get_hw_envelope_on $line]
				set hwEnvPeriod [get_hw_envelope_freqency $line]
				set hwEnvShape  [get_hw_envelope_shape $line]

				
				if {$fL > 0  && ($type == "fCA" || $type == "fCB" || $type == "mode")} {		
					set length $fL
					set ltmp $fL
					set noiseFreq    [get_noise_period $line]
					
					if {$noteCnt == 0} {
						switch $mode {
							0 {set mml "\n[expr $ch + $chOffset] \/0 v${v}"}
							1 {set mml "\n[expr $ch + $chOffset] \/1 s${hwEnvShape} m${hwEnvPeriod} v${v}"}
							2 {set mml "\n[expr $ch + $chOffset] \/2 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"} 
							3 {set mml "\n[expr $ch + $chOffset] \/3 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"}
						}
						puts "after node noteCnt:$noteCnt mml:$mml"
					}
						
					while {$length > 0} {
						if { $length > 255} {
							set ltmp 255
						} else {
							set ltmp $length
						}
							
						if {$mode == 0} {
							set v 0
						}

						if {$v != $vStamp && $noteCnt != 0} {
							set mml "${mml} v${v}"
						}
						
						if {$o != $oStamp} {
							set mml "${mml} o${o}"
						}
						
						set mml "${mml} ${scale}%${ltmp}"
						set lCnt [expr $lCnt + $ltmp]
						incr noteCnt
						
						set length [expr $length - $ltmp ]

						set oStamp $o
						set vStamp $v

					}
					if {$noteCnt == 8 || $mode == 0 } {
						lappend mmlBuffer1($ch) $mml
						set mml ""
						set info "\n;tick count: $lCnt\n"
						lappend mmlBuffer1($ch) $info
						set noteCnt 0
					}
					set oStamp $o
					set vStamp $v
				}
			}
		}
		
		if {$mml != "" } {
			lappend mmlBuffer1($ch) $mml
		}
			
		set info "\n;ch[expr $ch + $chOffset] end: tick count: $lCnt\n"
		lappend mmlBuffer1($ch) $info
	}

	proc generate_mml3 {} {
		variable chOffset
		variable num_of_ch
		variable workBuffer1
		variable workBuffer2
		variable mmlBuffer1
		variable mmlBuffer1F
		
		foreach ch $::mml_psg::chList {
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
				#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
				#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
				#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				set type       [lindex $line 0]
				set time       [lindex $line 1]
				set ch         [lindex $line 2]
				set ticks      [lindex $line 3]
				set l          [lindex $line 4]
				set fL         [lindex $line 5]
				set v          [lindex $line 6]
				set fV         [lindex $line 7]
				set f          [lindex $line 8]
				set fF         [lindex $line 9]
				set o          [lindex $line 10]
				set scale      [lindex $line 11]
				set mode       [lindex $line 12]
				set fMode      [lindex $line 13]
				set vDiff      [lindex $line 14]
				set vCnt       [lindex $line 15]
				set oDiff      [lindex $line 16]
				set envlp      [lindex $line 17]
				set envlpIndex [lindex $line 18]
				set nE         [lindex $line 19]
				set nF         [lindex $line 20]
				set noisePeriod [get_noise_period $line]
				set hwEnvOn     [get_hw_envelope_on $line]
				set hwEnvPeriod [get_hw_envelope_freqency $line]
				set hwEnvShape  [get_hw_envelope_shape $line]

				
				if {$fL > 0  && ($type == "fCA" || $type == "fCB" || $type == "mode")} {		
					set length $fL
					set ltmp $fL
					set noiseFreq    [get_noise_period $line]
					
					if {$noteCnt == 0} {
						switch $mode {
							0 {set mml "\n[expr $ch + $chOffset] \/0 v${v}"}
							1 {set mml "\n[expr $ch + $chOffset] \/1 s${hwEnvShape} m${hwEnvPeriod} v${v}"}
							2 {set mml "\n[expr $ch + $chOffset] \/2 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"} 
							3 {set mml "\n[expr $ch + $chOffset] \/3 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"}
						}
						puts "after node noteCnt:$noteCnt mml:$mml"
					}
						
					while {$length > 0} {
						if { $length > 255} {
							set ltmp 255
						} else {
							set ltmp $length
						}
							
						if {$mode == 0} {
							set v 0
						}

						if {$v != $vStamp && $noteCnt != 0} {
							set mml "${mml} v${v}"
						}
						
						if {$o != $oStamp} {
							set mml "${mml} o${o}"
						}
						
						set mml "${mml} ${scale}%${ltmp}"
						set lCnt [expr $lCnt + $ltmp]
						incr noteCnt
						
						set length [expr $length - $ltmp ]

						set oStamp $o
						set vStamp $v

					}
					if {$noteCnt == 8 || $en == 0 } {
						lappend mmlBuffer1($ch) $mml
						set mml ""
						set info "\n;tick count: $lCnt\n"
						lappend mmlBuffer1($ch) $info
						set noteCnt 0
					}
					set oStamp $o
					set vStamp $v
				}
			}
		}
		
		if {$mml != "" } {
			lappend mmlBuffer1($ch) $mml
		}
			
		set info "\n;ch[expr $ch + $chOffset] end: tick count: $lCnt\n"
		lappend mmlBuffer1($ch) $info
	}
	
	# Compute PSG mode (0=silent,1=tone,2=noise,3=tone+noise) from vVCtrl register.
	proc get_psg_mode { line } {
		set ch     [lindex $line 2]
		set vVCtrl [lindex $line 27]
		set mask   [expr {1 << $ch}]
		set noiseMute [expr {(($vVCtrl >> 3) & $mask) != 0}]
		set toneMute  [expr {($vVCtrl & $mask) != 0}]
		return [lindex {3 2 1 0} [expr {$noiseMute * 2 + $toneMute}]]
	}

	# Generate a single MGS-format note token from a workBuffer row.
	# cnt is at index 37 (appended by pass3).
	proc get_mml_MGS { line oStamp vStamp } {
		set l     [lindex $line 4]
		set v     [lindex $line 6]
		set o     [lindex $line 10]
		set scale [lindex $line 11]
		set vDiff [lindex $line 14]
		set cnt   [lindex $line 37]

		set oMML ""
		set oDiff [expr {$o - $oStamp}]
		if {$oDiff > 3 || $oDiff < -3} {
			set oMML "o$o"
		} else {
			if {$oDiff < 0} {
				while {$oDiff != 0} {
					set oMML "${oMML}\<"
					set oDiff [expr {$oDiff + 1}]
				}
			} elseif {$oDiff > 0} {
				while {$oDiff != 0} {
					set oMML "${oMML}\>"
					set oDiff [expr {$oDiff - 1}]
				}
			}
		}

		set mml ""
		if {$cnt == 1} { set vDiff [expr {$v - $vStamp}] }
		if {$vDiff > 3 || $vDiff < -3} {
			set mml "${mml}v$v"
		} else {
			if {$vDiff < 0} {
				while {$vDiff != 0} {
					set mml "${mml}\("
					set vDiff [expr {$vDiff + 1}]
				}
			} elseif {$vDiff > 0} {
				while {$vDiff != 0} {
					set mml "${mml}\)"
					set vDiff [expr {$vDiff - 1}]
				}
			}
		}

		set body "${scale}"
		set length $l
		while {$length > 0} {
			if {$length >= 64} {
				set mml "${mml}${body}1"
				set length [expr {$length - 64}]
			} elseif {$length >= 48} {
				set mml "${mml}${body}2."
				set length [expr {$length - 48}]
			} elseif {$length >= 32} {
				set mml "${mml}${body}2"
				set length [expr {$length - 32}]
			} elseif {$length >= 16} {
				set mml "${mml}${body}4"
				set length [expr {$length - 16}]
			} elseif {$length >= 12} {
				set mml "${mml}${body}8."
				set length [expr {$length - 12}]
			} elseif {$length >= 8} {
				set mml "${mml}${body}8"
				set length [expr {$length - 8}]
			} elseif {$length >= 6} {
				set mml "${mml}${body}16."
				set length [expr {$length - 6}]
			} elseif {$length >= 4} {
				set mml "${mml}${body}16"
				set length [expr {$length - 4}]
			} elseif {$length == 3} {
				set mml "${mml}${body}32."
				set length [expr {$length - 3}]
			} elseif {$length == 2} {
				set mml "${mml}${body}32"
				set length [expr {$length - 2}]
			} elseif {$length == 1} {
				set mml "${mml}${body}"
				set length [expr {$length - 1}]
			} else {
				set mml "${mml}\[$body\]$length"
				set length 0
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

	# Generate MGS-format MML (with [...]N repeat compression) from a workBuffer.
	proc generate_mml_MGS {workBufferName mmlBufferName} {
		variable chOffset
		variable num_of_ch
		upvar $workBufferName workBuffer
		upvar $mmlBufferName mmlBuffer

		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set beginFlg 1
			set newLineFlg 0
			set noteCnt 0
			set lineNo 0
			set mml ""
			set lCnt 0
			set ticksCountFlg 0
			set oStamp 0
			set vStamp 0
			set cntStamp 0
			foreach line $workBuffer($ch) {
				set type        [lindex $line 0]
				set ticks       [lindex $line 3]
				set l           [lindex $line 4]
				set v           [lindex $line 6]
				set o           [lindex $line 10]
				set scale       [lindex $line 11]
				set cnt         [lindex $line 37]
				set mode        [get_psg_mode $line]
				set noisePeriod [get_noise_period $line]
				set hwEnvOn     [get_hw_envelope_on $line]
				set hwEnvPeriod [get_hw_envelope_freqency $line]
				set hwEnvShape  [get_hw_envelope_shape $line]
				# Fix: define noiseFreq before the switch to avoid undefined-variable error
				set noiseFreq   $noisePeriod

				puts "; $line"
				if {$l != 0} {
					if {($type == "mode" || $type == "fCA" || $type == "fCB" || $type == "aVC" || $type == "wNC" || $type == "vVC" || $type == "ePL" || $type == "evM" || $type == "evS")} {
						set ticksCountFlg 1
						if {$beginFlg || $noteCnt == 0} {
							if {$mml != ""} {
								lappend mmlBuffer($ch) $mml
							}
							switch $mode {
								0 {set v 0; set mml "\n[expr {$ch + $chOffset}] \/0 v${v}"}
								1 {set mml "\n[expr {$ch + $chOffset}] \/1 s${hwEnvShape} m${hwEnvPeriod} v${v}"}
								2 {set mml "\n[expr {$ch + $chOffset}] \/2 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"}
								3 {set mml "\n[expr {$ch + $chOffset}] \/3 s${hwEnvShape} m${hwEnvPeriod} n${noiseFreq} v${v}"}
							}
							puts "after note noteCnt:$noteCnt mml:$mml"
							lappend mmlBuffer($ch) $mml
							set oStamp $o
							set vStamp $v
							set beginFlg 0
							set newLineFlg 1
						}

						set note [get_mml_MGS $line $oStamp $vStamp]
						set mml ${mml}${note}
						incr noteCnt

						if {$noteCnt > 8} {
							lappend mmlBuffer($ch) $mml
							set mml ""
							set noteCnt 0
							set newLineFlg 1
						}

						if {$mode == 0} {
							lappend mmlBuffer($ch) $mml
							set tmp "; Ticks count: $ticks"
							puts $tmp
							lappend mmlBuffer($ch) $tmp
							set mml ""
							set noteCnt 0
							set newLineFlg 1
							set ticksCountFlg 0
						}
					}
					set oStamp $o
					set vStamp $v
					set cntStamp $cnt
				} else {
					if {$ticksCountFlg && $mode == 0} {
						set tmp "; Ticks count: $ticks"
						puts $tmp
						lappend mmlBuffer($ch) $tmp
						set ticksCountFlg 0
					}
				}
			}
			set tmp ""
			lappend mmlBuffer($ch) $tmp
		}
	}

	# Re-compute and optimise the cnt repeat counter in workBuffer rows.
	# cnt is stored at index 37.  Repeat detection requires that type, f, l, o,
	# vDiff, mode, noisePeriod, hwEnvShape and hwEnvPeriod all match the
	# previous qualifying row.  Only fCA/fCB/aVC event types are considered.
	proc update_and_optimize_cnt {srcWorkBufferName dstWorkBufferName} {
		variable num_of_ch

		upvar $srcWorkBufferName srcBuffer
		upvar $dstWorkBufferName dstBuffer

		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			set lineNo 0
			set lineStamp ""
			set fStamp ""
			set lStamp ""
			set oStamp ""
			set scaleStamp ""
			set vDiffStamp 0
			set modeStamp ""
			set noisePeriodStamp ""
			set hwEnvShapeStamp ""
			set hwEnvPeriodStamp ""
			set cntStamp 0
			foreach line $srcBuffer($ch) {
				set type  [lindex $line 0]
				set l     [lindex $line 4]
				set f     [lindex $line 8]
				set o     [lindex $line 10]
				set scale [lindex $line 11]
				set vDiff [lindex $line 14]
				set cnt   [lindex $line 37]
				set mode        [get_psg_mode $line]
				set noisePeriod [get_noise_period $line]
				set hwEnvShape  [get_hw_envelope_shape $line]
				set hwEnvPeriod [get_hw_envelope_freqency $line]

				# Reset stamps when a fCA/fCB event silences the channel
				if {($type == "fCA" || $type == "fCB") && $mode == 0} {
					set lineStamp ""
					set fStamp ""
					set lStamp ""
					set oStamp ""
					set scaleStamp ""
					set vDiffStamp 0
					set modeStamp ""
					set noisePeriodStamp ""
					set hwEnvShapeStamp ""
					set hwEnvPeriodStamp ""
					set cntStamp 0
				}

				if {$l != 0} {
					if {$type == "fCA" || $type == "fCB" || $type == "aVC"} {
						puts "$f:$fStamp | $l:$lStamp | $o:$oStamp | $vDiff:$vDiffStamp | $mode:$modeStamp | $noisePeriod:$noisePeriodStamp"
						if {$f == $fStamp && $l == $lStamp && $o == $oStamp && $vDiff == $vDiffStamp && \
							$mode == $modeStamp && $noisePeriod == $noisePeriodStamp && \
							$hwEnvShape == $hwEnvShapeStamp && $hwEnvPeriod == $hwEnvPeriodStamp} {
							set cnt [incr cntStamp]
							puts "cnt"
							set line [lreplace $line 37 37 $cnt]
							puts "Original: [lindex $dstBuffer($ch) end]"
							puts "---->new: $line"
							set dstBuffer($ch) [lreplace $dstBuffer($ch) end end $line]
							puts "Replaced: [lindex $dstBuffer($ch) end]"
						} else {
							lappend dstBuffer($ch) $line
						}
					} else {
						lappend dstBuffer($ch) $line
					}

					set lineStamp $line
					set fStamp $f
					set lStamp $l
					set oStamp $o
					set scaleStamp $scale
					set vDiffStamp $vDiff
					set modeStamp $mode
					set noisePeriodStamp $noisePeriod
					set hwEnvShapeStamp $hwEnvShape
					set hwEnvPeriodStamp $hwEnvPeriod
					set cntStamp $cnt
				} else {
					lappend dstBuffer($ch) $line
				}
				incr lineNo
			}
		}
	}

	proc print_list {line} {
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		set type       [lindex $line 0]
		set time       [lindex $line 1]
		set ch         [lindex $line 2]
		set ticks      [lindex $line 3]
		set l          [lindex $line 4]
		set fL         [lindex $line 5]
		set v          [lindex $line 6]
		set fV         [lindex $line 7]
		set f          [lindex $line 8]
		set fF         [lindex $line 9]
		set o          [lindex $line 10]
		set scale      [lindex $line 11]
		set en         [lindex $line 12]
		set fEn        [lindex $line 13]
		set vDiff      [lindex $line 14]
		set vCnt       [lindex $line 15]
		set oDiff      [lindex $line 16]
		set envlp      [lindex $line 17]
		set envlpIndex [lindex $line 18]
		set nE         [lindex $line 19]
		set nF         [lindex $line 20]
		set noisePeriod [get_noise_period $line]
		set hwEnvOn     [get_hw_envelope_on $line]
		set hwEnvPeriod [get_hw_envelope_freqency $line]
		set hwEnvShape  [get_hw_envelope_shape $line]


		# 0    1    2  3    4  5  6 7  8     9 10 11    12     13   14      15          16         17          18     19     20     21     22     23        24        25          26       27
		#type,time,ch,ticks,l,fL,en,f,fStamp,v,o,scale,timbre,mode,hwEnvOn,hwEnvShape,hwEnvPeriod,noisePeriod,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		puts "type:$type,time:$time,ch$:ch,ticks:$ticks,l:$l,fL:$fL,v:$v,fV:$fV,f:$f,fF:$fF,o:$o,scale:$scale,en:$en,fEn:$fEn,vDiff:$vDiff,vCnt:$vCnt,oDiff:$oDiff,envlp:$envlp,envlpIndex:$envlpIndex,nE:$nE,nF:$nF"

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
	
	proc is_ch_exist { target } {
		set is_exist 0
		foreach ch $::mml_psg::chList {
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
		set ::mml_psg::fileNameBody $output_name_body

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
		# Pass 0 Add Ticks
		# -------------------------------------------
		foreach ch $::mml_psg::chList {
			set lineStamp ""
			foreach line $logBuffer($ch) {
				puts "line $line"
				if {$line != ""} {
					#type,time,ch,ticks,length,en,mode,freq,vol,timbre,Octave,Scale,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2"
					set tmp  [split $line ","]
					set type [lindex $tmp 0]
					set time [lindex $tmp 1]
					set ticks [get_ticks $time]
					#lappend tmp $ticks
					set tmp [lreplace $tmp 3 3 $ticks]
					
					lappend tempBuffer0($ch) $tmp
					set lineStamp $line
				}
			}
		}

		# Dump tempBuffer0($ch) into the file
		set output_file_name ${::mml_psg::fileNameBody}.psg.pass0.csv
		set fd [open ${output_dir}/${output_file_name} w]
		
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
		#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
		#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
		puts $fd "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2"
		
		foreach ch $::mml_psg::chList {
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
		foreach ch $::mml_psg::chList {
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
			set fLineStamp ""
			set numOfBuffer [llength $tempBuffer0($ch)]
			for {set index 0 } { $index < $numOfBuffer } { incr index} {
				set line [lindex $tempBuffer0($ch) $index]
				set next [lindex $tempBuffer0($ch) [expr $index + 1]]
				if {$lineStamp != "" } {
					#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
					# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
					#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
					#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
					set lineTemp $lineStamp
					set currentType [lindex $line 0]
					set nextType    [lindex $next 0]
					set currentL [expr [lindex $line 3] - [lindex $lineStamp 3]]
					set nextL    [expr [lindex $next 3] - [lindex $line 3]]
					if {($currentType == "fCtrlA" || $currentType =="fCtrlB") && ($nextType == "fCtrlA" || $nextType =="fCtrlB" ) && $nextL == 0} {
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
					if {$type == "fCtrlA" || $type == "fCtrlB" ||$type == "aVCtrl"} {
						set fL [expr $fTicks - $fTickStamp]
						set fTickStamp $fTicks
						set lineTemp  [lreplace $lineTemp 5 5 $fL]
					}
					
					# v
					puts "Pass1 index：$index lineStamp: $lineStamp"
					set v [get_volume $lineStamp ]
					set lineTemp [lreplace $lineTemp 6 6 $v]
					
					# fV
					if {$type == "fCtrlA" || $type == "fCtrlB" || $type == "aVCtrl"} {
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
					
					if {$type == "fCtrlA" || $type == "fCtrlB"} {
						set fStamp $f
					}
					
					# o
					set o [::mml_util::get_octave $fF]
					set lineTemp [lreplace $lineTemp 10 10 $o]
					
					# Scale
					set scale [::mml_util::get_scale $fF]
					set lineTemp [lreplace $lineTemp 11 11 $scale]

					# mode
					set mode [get_enable $lineStamp ]
					set lineTemp [lreplace $lineTemp 12 12 $mode]

					# fEn
					set fMode $enStamp
					set lineTemp [lreplace $lineTemp 13 13 $fMode]
					if {$type == "fCtrlA" || $type == "fCtrlB"} {
						set enStamp $mode
					}
					
					# VDiff
					puts "VDiff: lineStamp: $lineStamp"
					set vDiff [expr [get_volume $line ] - [get_volume $lineStamp ]]
					set lineTemp [lreplace $lineTemp 14 14 $vDiff]
					
					# vCnt
					if {$type == "vVCtrl"} {
						incr vCnt
					}
					set lineTemp [lreplace $lineTemp 15 15 $vCnt]
					
					# oDiff
					set nextf [get_frequency_from_line $line ]
					set nextO [::mml_util::get_octave $nextf]
					set oDiff [expr $nextO - $o]
					set lineTemp [lreplace $lineTemp 16 16 $oDiff]
					
					# wtbIndex
					#set tim [get_wtbIndex_from_line $lineStamp ]
					#set lineTemp [lreplace $lineTemp 23 23 $tim]
					
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
				if {$type == "fCtrlA" || $type == "fCtrlB" } {
					set fStamp $f
					set vCnt 1
				}
				set lineStamp $line
			}
			
			foreach line $tempBuffer0($ch) {
				if {$lineStamp != "" } {
					if {$fLineStamp == "" } {
						set fLineStamp $line
					}
					#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
					# 0    1    2  3    4  5 6  7 8  9 10 11   12  13  14    15   16    17    18        19 20   21    22    23      24     25     26     27     28     29        30        31        32         33
					#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
					#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
					set lineTemp $lineStamp
					set type     [lindex $lineStamp 0]
					set time     [lindex $lineStamp 1]
	
					#set l 
					set l [expr [lindex $line 3] - [lindex $lineStamp 3]]
					set lineTemp  [lreplace $lineTemp 4 4 $l]

					# fL
					set fL "-"
					set fTicks [lindex $lineStamp 3]
					if {$type == "fCA" || $type == "fCB"} {
						set fL [expr $fTicks - $fTickStamp]
						set fTickStamp $fTicks
					}
					set lineTemp  [lreplace $lineTemp 5 5 $fL]
				
					# en
					set en [get_enable $lineStamp ]
					set lineTemp [lreplace $lineTemp 6 6 $en]
									
					# f 
					set f [get_frequency_from_line $lineStamp ]
					set lineTemp [lreplace $lineTemp 7 7 $f]

					# fStamp
					set lineTemp [lreplace $lineTemp 8 8 $fStamp]
	
					# v
					puts "lineStamp: $lineStamp"
					set v [get_volume $lineStamp ]
					set lineTemp [lreplace $lineTemp 9 9 $v]
					
					# o
					set o [::mml_util::get_octave $f]
					if {$type == "fCA" || $type == "fCB"} {
						set o [::mml_util::get_octave $fStamp]
					}
					set lineTemp [lreplace $lineTemp 10 10 $o]
					
					# Scale
					set scale [::mml_util::get_scale $f]
					if {$type == "fCA" || $type == "fCB"} {
						set scale [::mml_util::get_scale $fStamp]
					}
					set lineTemp [lreplace $lineTemp 11 11 $scale]

					# Timbre
					set tim [get_timbre_index $lineStamp ]
					set lineTemp [lreplace $lineTemp 12 12 $tim]
							
					# hwEnvOn
					set hwEnvOn [get_hw_envelope_on $lineStamp ]
					set lineTemp [lreplace $lineTemp 14 14 $hwEnvOn]
					
					# hwEnvShape
					set hwEnvShape [get_hw_envelope_shape $lineStamp ]
					set lineTemp [lreplace $lineTemp 15 15 $hwEnvShape]

					# hwEnvPeriod
					set hwEnvPeriod [get_hw_envelope_freqency $lineStamp ]
					set lineTemp [lreplace $lineTemp 16 16 $hwEnvPeriod]

					# noisePeriod
					set noisePeriod [get_noise_period $lineStamp ]
					set lineTemp [lreplace $lineTemp 17 17 $noisePeriod]
					
					# Push lineTemp into tempBuffer1($ch)
					lappend tempBuffer1($ch) $lineTemp
				}
				if {$type == "fCA" || $type == "fCB"} {
					set fStamp $f
				}
				set lineStamp $line

			}
			# Last line
			#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
			# 0    1    2  3    4  5  6 7  8     9 10 11    12     13   14      15          16         17          18     19     20     21     22     23        24        25          26       27
			#type,time,ch,ticks,l,fL,en,f,fStamp,v,o,scale,timbre,mode,hwEnvOn,hwEnvShape,hwEnvPeriod,noisePeriod,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
			#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
			set lineTemp $lineStamp
			set time     [lindex $lineStamp 1]
			
			#set l 
			set l [expr [lindex $line 3] - [lindex $lineStamp 3]]
			set lineTemp  [lreplace $lineTemp 4 4 $l]

			# fL
			set fL "-"
			set fTicks [lindex $lineStamp 3]
			if {$type == "mode"} {
				set fL [expr $fTicks - $fTickStamp]
				set fTickStamp $fTicks
			}
			if {$type == "fCA" || $type == "fCB"} {
				set fL [expr $fTicks - $fTickStamp]
				set fTickStamp $fTicks
			}
			set lineTemp  [lreplace $lineTemp 5 5 $fL]
			
			# en
			set en [get_enable $lineStamp ]
			set lineTemp [lreplace $lineTemp 6 6 $en]
							
			# f 
			set lineTemp [lreplace $lineTemp 8 8 $fStamp]
			set f [get_frequency_from_line $lineStamp ]
			set lineTemp [lreplace $lineTemp 7 7 $f]
			set fStamp $f
			
			# v
			puts "Last Line: lineStamp: $lineStamp"
			set v [get_volume $lineStamp ]
			set lineTemp [lreplace $lineTemp 9 9 $v]
			
			# o
			set o [::mml_util::get_octave $f]
			if {$type == "fCA" || $type == "fCB" } {
				set o [::mml_util::get_octave $fStamp]
			}
			set lineTemp [lreplace $lineTemp 10 10 $o]
			
			# Scale
			set scale [::mml_util::get_scale $f]
			if {$type == "fCA" || $type == "fCB"} {
				set scale [::mml_util::get_scale $fStamp]
			}
			set lineTemp [lreplace $lineTemp 11 11 $scale]
			
			# Timbre
			set tim [get_timbre_index $lineStamp ]
			set lineTemp [lreplace $lineTemp 12 12 $tim]
					
			# hwEnvOn
			set hwEnvOn [get_hw_envelope_on $lineStamp ]
			set lineTemp [lreplace $lineTemp 14 14 $hwEnvOn]
			
			# hwEnvShape
			set hwEnvShape [get_hw_envelope_shape $lineStamp ]
			set lineTemp [lreplace $lineTemp 15 15 $hwEnvShape]
			
			# hwEnvPeriod
			set hwEnvPeriod [get_hw_envelope_freqency $lineStamp ]
			set lineTemp [lreplace $lineTemp 16 16 $hwEnvPeriod]
			
			# noisePeriod
			set noisePeriod [get_noise_period $lineStamp ]
			set lineTemp [lreplace $lineTemp 17 17 $noisePeriod]
			
			# Push lineTemp into tempBuffer1($ch)
			lappend tempBuffer1($ch) $lineTemp
		}
		
		# Dump tempBuffer1($ch) into the file
		set output_file_name ${output_name_body}.psg.pass1.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts "::mml_psg::chList $::mml_psg::chList"
		puts $fd "type,time,ch,ticks,l,fL,en,f,fStamp,v,o,scale,timbre,mode,hwEnvOn,hwEnvShape,hwEnvPeriod,noisePeriod,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2"
		foreach ch $::mml_psg::chList {
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
		foreach ch $::mml_psg::chList {
			foreach tmp $tempBuffer1($ch) {
				#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5  6 7  8     9 10 11    12     13   14      15          16         17          18     19     20     21     22     23        24        25          26       27
				#type,time,ch,ticks,l,fL,en,f,fStamp,v,o,scale,timbre,mode,hwEnvOn,hwEnvShape,hwEnvPeriod,noisePeriod,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
				#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				set type  [lindex $tmp 0]
				set l     [lindex $tmp 4]

				if { $l != 0  } {
					lappend tempBuffer2($ch) $tmp
				} else {
					if { $type == "mode" ||$type == "fCA" || $type == "fCB"} {
						lappend tempBuffer2($ch) $tmp
					}
				}
			}
		}
		
		# Dump tempBuffer2($ch) into the file
		set output_file_name ${output_name_body}.psg.pass2.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,ticks,l,fL,en,f,fStamp,v,o,scale,timbre,mode,hwEnvOn,hwEnvShape,hwEnvPeriod,noisePeriod,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2"
		foreach ch $::mml_psg::chList {
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
		foreach ch $::mml_psg::chList {
			set lStamp 0
			set vStamp 0
			set oStamp 0
			set cnt    0
			set lDiffStamp 0
			set vDiffStamp 0
			set oDiffStamp 0
			set cntStamp   0
			set cnt 1
			foreach tmp $tempBuffer2($ch) {
				#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				# 0    1    2  3    4  5  6 7  8     9 10 11    12     13   14      15          16         17          18     19     20     21     22     23        24        25          26       27
				#type,time,ch,ticks,l,fL,en,f,fStamp,v,o,scale,timbre,mode,hwEnvOn,hwEnvShape,hwEnvPeriod,noisePeriod,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2
				#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
				set l     [lindex $tmp 4]
				set lDiff [expr $l - $lStamp]
				lappend tmp $lDiff	

				# fL
				set fL   [lindex $tmp 5]
				
				if {$vStamp != ""} {
				set v     [lindex $tmp 9]
				set vDiff [expr $v - $vStamp]
				} else {
				set vDiff NA
				}
				lappend tmp $vDiff
				
				set o [lindex $tmp 10]
				set oDiff [expr $o - $oStamp]
				lappend tmp $oDiff
				
				
				if { $lDiff == 0 && $vDiffStamp == $vDiff} {
					incr cnt
				} else {
					set cnt 1
				}
				lappend tmp $cnt
				
				lappend tempBuffer3($ch) $tmp
				set lStamp $l
				set vStamp $v
				set oStamp $o
				set lDiffStamp $lDiff	
				set vDiffStamp $vDiff
				set oDiffStamp $oDiff
			}
		}
		# Dump tempBuffer3($ch) into the file
		set output_file_name ${output_name_body}.psg.pass3.csv
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd "#type,time,ch,ticks,l,fL,en,f,fStamp,v,o,scale,timbre,mode,hwEnvOn,hwEnvShape,hwEnvPeriod,noisePeriod,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2,vDiff,oDiff,cnt"
		foreach ch $::mml_psg::chList {
			foreach line $tempBuffer3($ch) {
				set tmp  [regsub -all " " $line ","]
				puts $fd $tmp
			}
		}
		close $fd

		# Copy tempBuffer3 to workBuffer1
		for {set ch 0} {$ch < $num_of_ch} {incr ch} {
			foreach line $tempBuffer3($ch) {
				lappend workBuffer1($ch) $line
			}
		}
		# generate_mml: Generate mml based on workBuffer2
		generate_mml
		
		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${output_name_body}.psg.pass3.mml
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd ";\[name=scc lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"psg example\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""
		foreach ch $::mml_psg::chList {
			foreach line $mmlBuffer1($ch) {
				puts -nonewline $fd $line
			}
		}
		close $fd

		# generate_mml: Read workBuffer2 and generate mml into mmlBuffer1
		generate_mml

		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${output_name_body}.psg.pass3_1.mml
		set fd [open ${output_dir}/${output_file_name} w]
		
		puts $fd ";\[name=scc lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"$::mml_psg::fileNameBody\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""
		foreach ch $::mml_psg::chList {
			foreach line $mmlBuffer1($ch) {
				puts $fd $line
			}
		}
		close $fd	
		
		# generate_mml: Read workBuffer2 and generate mml into mmlBuffer1
		array unset  mmlBuffer1
		generate_mml2

		# Dump mmlBuffer1($ch) into the file
		set output_file_name ${output_name_body}.psg.pass3_2.mml
		set fd [open ${output_dir}/${output_file_name} w]
		
		puts $fd ";\[name=scc lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"$::mml_psg::fileNameBody\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""		
		foreach ch $::mml_psg::chList {
			foreach line $mmlBuffer1($ch) {
				puts $fd $line
			}
		}
		close $fd

		# Generate .pass3.simple.MGS.mml (uncompressed MGS format)
		array unset mmlBuffer1
		generate_mml_MGS workBuffer1 mmlBuffer1

		set output_file_name ${output_name_body}.psg.pass3.simple.MGS.mml
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd ";\[name=psg lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"$::mml_psg::fileNameBody\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""
		foreach ch $::mml_psg::chList {
			foreach line $mmlBuffer1($ch) {
				puts $fd $line
			}
		}
		close $fd

		# Generate .pass3.compress.MGS.mml (cnt-optimised [...]N repeat compression)
		update_and_optimize_cnt workBuffer1 workBuffer2
		array unset mmlBuffer1
		generate_mml_MGS workBuffer2 mmlBuffer1

		set output_file_name ${output_name_body}.psg.pass3.compress.MGS.mml
		set fd [open ${output_dir}/${output_file_name} w]
		puts $fd ";\[name=psg lpf=1\]"
		puts $fd "#opll_mode 1"
		puts $fd "#tempo 75"
		puts $fd "#title { \"$::mml_psg::fileNameBody\"}"
		puts $fd "#alloc 1=3100"
		puts $fd "#alloc 2=3100"
		puts $fd "#alloc 3=2400"
		puts $fd "#alloc 4=2100"
		puts $fd "#alloc 5=1100"
		puts $fd "#alloc 6=1000"
		puts $fd "#alloc 7=1000"
		puts $fd ""
		foreach ch $::mml_psg::chList {
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

::mml_psg::extrac_to_csv $directory $filename


