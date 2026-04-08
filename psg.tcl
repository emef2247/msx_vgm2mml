set script_dir [file dirname [file normalize [info script]]]
source ${script_dir}/mml_utils.tcl


namespace eval psg {

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
	variable chStamp  0
	variable num_of_ch 3
	variable offset_of_ch 0
	
	variable timbreList  [list]
	variable timbreIndex 0
	# ----------------------------
	# Register access flags
	# ----------------------------
	variable chAllData ""
	variable ch1Data ""
	variable ch2Data ""
	variable ch3Data ""

	variable IsfCtrlASet 0
	variable IsfCtrlBSet 0
	variable IswNCtrlSet 0
	variable IsvVCtrlSet 0
	variable IsaVCtrlSet 0
	variable IsaVCtrlSet 0
	variable IsenvPCtrlLSet 0
	variable IsenvPCtrlMSet 0
	variable IsenvShapeSet  0
	variable IsioParallel1Set  0
	variable IsioParallel2Set  0

	# ----------------------------
	# Time Information
	# ----------------------------
	array set time {}
	array set timeStamp {}

	array set ticks {}
	array set ticksStamp {}

	array set type {}
	array set typeStamp {}
	
	
	# ----------------------------
	# Noise and Voice Output
	# ----------------------------
	array set psgMode {}
	array set psgModeStamp {}

	# ----------------------------
	# Frequency control registers
	# ----------------------------
	array set fCtrlA {}
	array set fCtrlAStamp {}
	array set fCtrlB {}
	array set fCtrlBStamp {}
	
	# ----------------------------------------
	# White noise frequency control register
	# ----------------------------------------
	array set wNCtrl {}
	array set wNCtrlStamp {}

	# ----------------------------------------
	# PSG voice and I/O port control register
	# ----------------------------------------
	array set vVCtrl {}
	array set vVCtrlStamp {}

	# ----------------------------------------
	# Amplitude and volume control registers
	# ----------------------------------------
	array set aVCtrl {}
	array set aVCtrlStamp {}

	# -------------------------------------------
	# Envelope Form and Period Control Registers
	# -------------------------------------------
	array set envPCtrlL {}
	array set envPCtrlLStamp {}
	array set envPCtrlM {}
	array set envPCtrlMStamp {}
	array set envShape  {}
	array set envShapeStamp  {}

	# ---------------------------------
	# PSG I/O Parallel Port Registers
	# ---------------------------------
	array set ioParallel1  {}
	array set ioParallel1Stamp  {}
	array set ioParallel2  {}
	array set ioParallel2Stamp  {}

	array set bufferAccessLog {}
	variable bufferAccessTrace 0

	proc init { is_scc_plus } {
		puts "[getGlobalTime] [getTime] ([getTicks $::psg::commonTime]]) init $is_scc_plus"
		set ::psg::tempo 75
		set ::psg::globalTime 0
		set ::psg::commonTime 0
		set ::psg::commonTimeStamp 0
		set ::psg::startTime 0
		
		set ::psg::l64 [expr (60.0 / $::psg::tempo) / 16]
		
		set ::psg::ch  0
		set ::psg::chStamp  0
		
		set ::psg::num_of_ch 3

		set ::psg::IsfCtrlASet 0
		set ::psg::IsfCtrlBSet 0
		set ::psg::IswNCtrlSet 0
		set ::psg::IsvVCtrlSet 0
		set ::psg::IsaVCtrlSet 0
		set ::psg::IsenvPCtrlLSet 0
		set ::psg::IsenvPCtrlMSet 0
		set ::psg::IsenvShapeSet  0
		set ::psg::IsioParallel1Set  0
		set ::psg::IsioParallel2Set  0

		set ::psg::bufferAccessTrace ""
		set ::psg::header ""

		for {set ch 0} {$ch < $::psg::num_of_ch} {incr ch} {
			set ::psg::time($ch) 0
			set ::psg::timeStamp($ch) 0
			
			set ::psg::ticks($ch) 0
			set ::psg::ticksStamp($ch) 0

			set ::psg::type($ch) 0
			set ::psg::typeStamp($ch) 0
			
			set ::psg::psgMode($ch) 0
			set ::psg::psgModeStamp($ch) 0
	
			# ----------------------------------------
			# White noise frequency control register
			# ----------------------------------------
			set ::psg::wNCtrl($ch) 0
			set ::psg::wNCtrlStamp($ch) 0
		
			# ----------------------------
			# Frequency control registers
			# ----------------------------
			set ::psg::fCtrlA($ch) 0
			set ::psg::fCtrlAStamp($ch) 0
			set ::psg::fCtrlB($ch) 0
			set ::psg::fCtrlBStamp($ch) 0
			
			set ::psg::fCtrlA(0) 85
			set ::psg::fCtrlAStamp(0) 85

			# ----------------------------------------
			# White noise frequency control register
			# ----------------------------------------
			set ::psg::wNCtrl($ch) 0
			set ::psg::wNCtrlStamp($ch) 0

			# ----------------------------------------
			# PSG voice and I/O port control register
			# ----------------------------------------
			set ::psg::vVCtrl($ch) 187
			set ::psg::vVCtrlStamp($ch) 187
		
			# ----------------------------------------
			# Amplitude and volume control registers
			# ----------------------------------------
			set ::psg::aVCtrl($ch) 0
			set ::psg::aVCtrlStamp($ch) 0

			# -------------------------------------------
			# Envelope Form and Period Control Registers
			# -------------------------------------------
			set ::psg::envPCtrlL($ch) 11
			set ::psg::envPCtrlLStamp($ch) 11
			set ::psg::envPCtrlM($ch) 0
			set ::psg::envPCtrlMStamp($ch) 0
			set ::psg::envShape($ch) 0
			set ::psg::envShapeStamp($ch) 0

			# ---------------------------------
			# PSG I/O Parallel Port Registers
			# ---------------------------------
			set ::psg::ioParallel1($ch)  0
			set ::psg::ioParallel1Stamp($ch)  0
			set ::psg::ioParallel2($ch)  0
			set ::psg::ioParallel2Stamp($ch)  0
		
			set ::psg::bufferAccessLog($ch) [list]
		}
	}
	
	
	proc updateTime {time_s} {
		puts "[getGlobalTime] [getTime] ([getTicks $::psg::commonTime]]) updateTime $time_s"
		set ::psg::globalTime $time_s
		
		if {$::psg::startTime == 0} {
			set ::psg::startTime $time_s
		}
		
		# Update ::psg::commonTime
		set ::psg::commonTimeStamp $::psg::commonTime
		set ::psg::commonTime [expr $time_s - $::psg::startTime]
		
		set ::psg::deltaTime [expr $::psg::commonTime - $::psg::commonTimeStamp]
	}
	
	proc getDeltaTime {} {
		return $::psg::deltaTime
	}
	
	proc getGlobalTime {} {
		return $::psg::globalTime
	}
	
	proc getTime {} {
		return $::psg::commonTime
	}
	
	proc getTicks { time_s } {
		variable l64
		puts "getTicks time_s=$time_s"
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
	
	proc getPsgMode {ch reg} {
		# Noise Mute
		set noiseMute [expr ($reg / 8) & 0x7]
		set mask 1
		switch $ch {
		0 {set mask 1}
		1 {set mask 2}
		2 {set mask 4}
		}
		
		set isNoiseMute 0
		if {[expr $noiseMute & $mask] == $mask } {
			set isNoiseMute 1
		}
		
		# Tone Mute
		set toneMute [expr $reg & 0x7]
		set mask 1
		switch $ch {
		0 {set mask 1}
		1 {set mask 2}
		2 {set mask 4}
		}
		
		set isToneMute 0
		if {[expr $toneMute & $mask] == $mask } {
			set isToneMute 1
		}

		# Mode
		set noiseMute_voiceMute [expr ($isNoiseMute *2) + $isToneMute]
		set mode 0
		switch $noiseMute_voiceMute {
			0 {set mode 3} #No Mute    --> Output Noise & Tone
			1 {set mode 2} #Mute Tone  --> Output Noise
			2 {set mode 1} #Mute Noise --> Output Tone
			3 {set mode 0} #Mute Both  --> No Output
		}
		
		return $mode
	}
	
	proc write {time_s wp_last_address  wp_last_value } {
		puts "[getGlobalTime] [getTime] ([getTicks $::psg::commonTime]]) WriteLog"

		# PSG Registers
		# https://www.msx.org/wiki/PSG_Registers
		#
		# ----------------------------
		# Frequency control registers
		# ----------------------------
		# Register 0 [7:4 least significant bits of voice frequency 1   ]
		# Register 1 [7:4][3:0 most signifiant bits of voice frequency 1]
		# Register 2 [7:4 least significant bits of voice frequency 2   ]
		# Register 3 [7:4][3:0 most signifiant bits of voice frequency 2]
		# Register 4 [7:4 least significant bits of voice frequency 3   ]
		# Register 5 [7:4][3:0 most signifiant bits of voice frequency 3]
		# Value = Fi / (16 x Fb)
		# Fi = Internal frequency of PSG (1789772.5 Hz on MSX)
		# Fb = Tone frequency master to be produced (varies between between 27 and 111.860 Hz)
		#
		# ----------------------------------------
		# White noise frequency control register
		# ----------------------------------------
		# Register 6 [7:5][4:0 White noise generator frequency]
		# Value = Fi / 16 x Fb
		# Fi = PSG internal frequency (1789772.5 Hz)
		# Fb = Base frequency of the noise to be produced (varies between 3.608 and 111.860 Hz)
		#
		# ----------------------------------------
		# PSG voice and I/O port control register
		# ----------------------------------------
		# Register 7　[7 B = 1][6 A = 0][5 voice 3][4 voice 2][3 voice 1][2 voice 3][1 voice 2][0 voice 1]
		# To make mute the sound on a voice, you can set the volume of the voice to 0 (registers 8 to 10) or deactivate the tone and noise generator of this voice by setting the corresponding bits of register 7 to 1.
		# In order to guarantee the proper functioning of the PSG I/O ports, bit 7 of register 7 must always remain at 1 (port B in output mode) and bit 6 at 0 (port A in input mode).
		# It is therefore possible to enable the sound generator and the noise generator at the same time on each voice. That is to say, mix the two.
		#
		# ----------------------------------------
		# Amplitude and volume control registers
		# ----------------------------------------
		# Register  8 [7:5][4 V/A][3:0 Voice Volume / Amplitude 1]
		# Register  9 [7:5][4 V/A][3:0 Voice Volume / Amplitude 2]
		# Register 10 [7:5][4 V/A][3:0 Voice Volume / Amplitude 3]
		# Reset bit 4 (V/A) to adjust the sound volume of the corresponding voice. When bit 4 (V/A) is set, the volume will vary in proportion to the shape of the envelope defined by register 13
		#
		# -------------------------------------------
		# Envelope Form and Period Control Registers
		# -------------------------------------------
		# Register 11 [7:0 least significant bits of the value that determines the envelope period (T)]
		# Register 12 [7:0 least significant bits of the value that determines the envelope period (T)]
		# Register 13 [7:4][3:0 Envelope shape]
		# Registers 11 and 12 control the envelope period. The value is on 16 bits (0~65535). It is calculated with the following expression:
		# Value = Fi / (256 x T)
		# Fi = Internal frequency of PSG (1789772.5 Hz on MSX)
		# T = Period of the envelope (in μs)
		# The register 13 defines the envelope shape. Here are the possible shapes:
		# Bits detail:
		# Bit 0 (Hold) specifies whether the period should be repetitive or not.
		# Bit 1 (Alternate) specifies whether or not the shape of the envelope should be inverted on each repetition.
		# Bit 2 (Attack) specifies whether or not to invert the shape of the envelope.
		# Bit 3 (Continue) specifies that the shape of the envelope should remain at the same level at the end of the period.
		#
		# ---------------------------------
		# PSG I/O Parallel Port Registers
		# ---------------------------------
		# Register 14 [7:0 Port parallel A of E/S of PSG (Always set as input with bit 6 of R#7)]
		# This register makes it possible to control the pins of the general ports to read via register 14 as well as the state of the LED "code" or "kana" depending on the type of keyboard.
		# Bit 0 = Pin 1 state of the selected general port (Up if joystick)
		# Bit 1 = Pin 2 state of the selected general port (Down if joystick)
		# Bit 2 = Pin 3 state of the selected general port (Left if joystick)
		# Bit 3 = Pin 4 state of the selected general port (Right if joystick)
		# Bit 4 = Pin 6 state of the selected general port (Trigger A if joystick)
		# Bit 5 = Pin 7 state of the selected general port (Trigger B if joystick)
		# Bit 6 = 1 for JIS keyboard, 0 for JP50on (only valid for Japanese MSX)
		# Bit 7 = CASRD (Reading signal on cassette)
		# Register 15 [7:0 Port parallel B of E/S of PSG (Always set as output with bit 7 of R#7)]
		# This register makes it possible to control the pins of the general ports to read via register 14 as well as the state of the LED "code" or "kana" depending on the type of keyboard.
		# 
		# Bit 0 = pin control 6 of the general port 1*
		# Bit 1 = pin control 7 of the general port 1*
		# Bit 2 = pin control 6 of the general port 2*
		# Bit 3 = pin control 7 of the general port 2*
		# Bit 4 = pin control 8 of the general port 1 (0 for standard joystick mode)
		# Bit 5 = pin control 8 of the general port 2 (0 for standard joystick mode)
		# Bit 6 = selection of the general port readable via register 14 (1 for port 2)
		# Bit 7 = LED control of the "Code" or "Kana" key. (1 to turn off)
		# (*) Put to 1 if the general port is used as a starter (reading).


		set ::psg::ch all
		switch $wp_last_address {
			 0 {set ::psg::IsfCtrlASet 1;set ::psg::ch 0}
			 1 {set ::psg::IsfCtrlBSet 1;set ::psg::ch 0}
			 2 {set ::psg::IsfCtrlASet 1;set ::psg::ch 1}
			 3 {set ::psg::IsfCtrlBSet 1;set ::psg::ch 1}
			 4 {set ::psg::IsfCtrlASet 1;set ::psg::ch 2}
			 5 {set ::psg::IsfCtrlBSet 1;set ::psg::ch 2}
			 6 {set ::psg::IswNCtrlSet 1}
			 7 {set ::psg::IsvVCtrlSet 1}
			 8 {set ::psg::IsaVCtrlSet 1;set ::psg::ch 0}
			 9 {set ::psg::IsaVCtrlSet 1;set ::psg::ch 1}
			10 {set ::psg::IsaVCtrlSet 1;set ::psg::ch 2}	
			11 {set ::psg::IsenvPCtrlLSet 1}			
			12 {set ::psg::IsenvPCtrlMSet 1}			
			13 {set ::psg::IsenvShapeSet  1}			
			14 {set ::psg::IsioParallel1Set  1}			
			15 {set ::psg::IsioParallel2Set  1}			
			default {puts "Invalid Address: $wp_last_address"}
		}

		::psg::updateTime $time_s
		set trace [::psg::updateRegisters $::psg::ch $wp_last_value]
		
		return $trace
	}
	
	proc updateRegisters { index regValue } {
		puts "[getGlobalTime] [getTime] ([getTicks $::psg::commonTime]]) updateRegisters $index $regValue"

		set type unkown
		set trace ""
		if {$index == "all" } {
			for {set ch 0} {$ch < $::psg::num_of_ch} {incr ch} {
				if {$::psg::IswNCtrlSet} {
					set type wNC
					set ::psg::wNCtrlStamp($ch) $::psg::wNCtrl($ch)
					set ::psg::wNCtrl($ch) $regValue
					
					set trace [accessLogInCsv $ch $type]
				}
			
				if {$::psg::IsvVCtrlSet } {
					set type vVC
					set ::psg::vVCtrlStamp($ch) $::psg::vVCtrl($ch)
					set ::psg::vVCtrl($ch) $regValue
					
					set mode [getPsgMode $ch $regValue]
					if {$mode != $::psg::psgMode($ch) } {
						set ::psg::psgModeStamp($ch) $::psg::psgMode($ch)
						set ::psg::psgMode($ch) $mode
						set type mode
						
						set trace [accessLogInCsv $ch $type]
					}
				}
			
				if {$::psg::IsenvPCtrlLSet} {
					set type ePL
					set ::psg::envPCtrlLStamp($ch) $::psg::envPCtrlL($ch)
					set ::psg::envPCtrlL($ch) $regValue
					
					set trace [accessLogInCsv $ch $type]
				}
		
				if {$::psg::IsenvPCtrlMSet} {
					set type evM
					set ::psg::envPCtrlMStamp($ch) $::psg::envPCtrlM($ch)
					set ::psg::envPCtrlM($ch) $regValue
					
					set trace [accessLogInCsv $ch $type]
				}
				
				if {$::psg::IsenvShapeSet} {
					set type evS
					set ::psg::envShapeStamp($ch) $::psg::envShape($ch)
					set ::psg::envShape($ch) $regValue
					
					set trace [accessLogInCsv $ch $type]
				}
				
				if {$::psg::IsioParallel1Set} {
					set type io1
					set ::psg::ioParallel1Stamp($ch) $::psg::ioParallel1($ch)
					set ::psg::ioParallel1($ch) $regValue
					
					set trace [accessLogInCsv $ch $type]
				}
				
				if {$::psg::IsioParallel2Set} {
					set type io2
					set ::psg::ioParallel2Stamp($ch) $::psg::ioParallel2($ch)
					set ::psg::ioParallel2($ch)      $regValue
					
					set trace [accessLogInCsv $ch $type]
				}
			}
		} else {
			set ch $index
			if {$::psg::IsfCtrlASet} {
				set type fCA
				set ::psg::fCtrlAStamp($ch) $::psg::fCtrlA($ch)
				set ::psg::fCtrlA($ch) $regValue
				
				set trace [accessLogInCsv $ch $type]
			}
		
			if {$::psg::IsfCtrlBSet} {
				set type fCB
				set ::psg::fCtrlBStamp($ch) $::psg::fCtrlB($ch)
				set ::psg::fCtrlB($ch) $regValue
				
				set trace [accessLogInCsv $ch $type]
			}
		
			if {$::psg::IsaVCtrlSet} {
				set type aVC
				set ::psg::aVCtrlStamp($ch) $::psg::aVCtrl($ch)
				set ::psg::aVCtrl($ch) $regValue
				
				set trace [accessLogInCsv $ch $type]
			}
		}

		# Clear all flags
		set ::psg::IsfCtrlASet 0
		set ::psg::IsfCtrlBSet 0
		set ::psg::IswNCtrlSet 0
		set ::psg::IsvVCtrlSet 0 
		set ::psg::IsaVCtrlSet 0
		set ::psg::IsenvPCtrlLSet 0
		set ::psg::IsenvPCtrlMSet 0
		set ::psg::IsenvShapeSet  0
		set ::psg::IsioParallel1Set  0	
		set ::psg::IsioParallel2Set  0
		
		return $trace
	}
	

	proc getTimbre {mode noisePeriod hwEnvelopeOn hwEnvelopeFreqency hwEnvelopeShape } {
		set timbre "${mode},${noisePeriod},${hwEnvelopeOn},${hwEnvelopeFreqency},${hwEnvelopeShape}"
		return $timbre
	}
	
	proc isTimbreExist { voice } {
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
	
	proc getTimbreIndex { timbre } {
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
	

	# Get the calculated frequency from the register value
	# If the value of the register is 0, the highest value (111860.78125 for AY-3-8910) is returned.
	proc getToneFreqency {reg16} {
		if { $reg16 == 0} { return [expr int(111860.78125)] }
		return [expr int(111860.78125/$reg16)]
	}
	
	proc getFRegValue16 {fCtrlA  fCtrlB} {
		#set fCtrlA [lindex $line 24]
		#set fCtrlB [lindex $line 25]
		#puts ""
		set f [expr $fCtrlA + (256*$fCtrlB)]
		return $f
	}
	
	proc getVolume {  aVCtrl } {
		#set aVCtrl    [lindex $line 28]
		set v [expr $aVCtrl & 0xf ]
		return $v
	}
	
	proc getNoisePeriod { wNCtrl } {
		set noisePeriod  [expr $wNCtrl & 0x1f]
		return $noisePeriod
	}
	
	proc getHwEnvelopeOn { aVCtrl } {

		set hwENvOn [expr $aVCtrl / 16]
		
		return $hwENvOn
	}
	
	proc getHwEnvelopeFreqency { envPCtrlL  envPCtrlM} {
		set envPeriod [expr ($envPCtrlM *256) + $envPCtrlL]
		
				
		# T =(256*EP)/fc =(256*EP)/1.7897725 [MHz] =143.03493*EP [μs]
		set envFrequency [expr int(143.03493 * $envPeriod) ]
		
		return $envFrequency
	}
	
	proc getHwEnvelopeShape { envShape } {
		set hwEnvelopeShape  [expr $envShape & 0xf]
		
		return $hwEnvelopeShape
	}
	
	
	proc accessLogInCsv {ch type} {
		
		set time $::psg::commonTime	
		set ::psg::timeStamp($ch) $::psg::time($ch)
		set ::psg::time($ch) $time
		
		set ticks [getTicks $time]	
		set ::psg::ticksStamp($ch) $::psg::ticks($ch)
		set ::psg::ticks($ch) $ticks

		set ::psg::typeStamp($ch) $::psg::type($ch)
		set ::psg::type($ch) $type
		
		set fCtrlA $::psg::fCtrlA($ch)
		set fCtrlB $::psg::fCtrlB($ch)
		set wNCtrl $::psg::wNCtrl($ch)
		set vVCtrl $::psg::vVCtrl($ch)
		set aVCtrl $::psg::aVCtrl($ch)
		set envPCtrlL $::psg::envPCtrlL($ch)
		set envPCtrlM $::psg::envPCtrlM($ch)
		set envShape  $::psg::envShape($ch)
		set ioParallel1 $::psg::ioParallel1($ch)
		set ioParallel2 $::psg::ioParallel2($ch)
		set mode $::psg::psgMode($ch)
		
		set fReg16      [getFRegValue16 $fCtrlA $fCtrlB]
		set volume      [getVolume $aVCtrl]
		
		set freqency    [::mml_util::getToneFreqency $fReg16]
		set noteNumber  [::mml_util::frequencyToMidiNote $freqency]
		
		# Timbre
		set noisePeriod        [getNoisePeriod $wNCtrl]
		set hwEnvelopeOn       [getHwEnvelopeOn $aVCtrl]
		set hwEnvelopeFreqency [getHwEnvelopeFreqency $envPCtrlL  $envPCtrlM]
		set hwEnvelopeShape    [getHwEnvelopeShape $envShape]

		set timbre             [getTimbre $mode $noisePeriod $hwEnvelopeOn $hwEnvelopeFreqency $hwEnvelopeShape]
		set timbreIndex        [getTimbreIndex $timbre]


		set line "$type,$time,$ch,$ticks,,,,,,,,,$mode,,,,,,,,,,,,,$fCtrlA,$fCtrlB,$wNCtrl,$vVCtrl,$aVCtrl,$envPCtrlL,$envPCtrlM,$envShape,$ioParallel1,$ioParallel2"
		lappend ::psg::bufferAccessLog($ch) $line
		lappend ::psg::bufferAccessTrace $line
		
		set trace "$type,$time,$ch,$ticks,$noteNumber,$freqency,$volume,$timbreIndex"
		return $trace
	}
	
	proc outputCsv {directory file_name} {
		set log_csv_file_name [format %s%s [file rootname $file_name] "_log.psg.csv"]
		set log_csv_file_handle [open $log_csv_file_name "w"]
		
		set header "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,cnt,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2"

		puts $log_csv_file_handle $header
		for {set ch 0} {$ch < $::psg::num_of_ch} {incr ch} {			
			foreach line $::psg::bufferAccessLog($ch) {
				puts $log_csv_file_handle $line
			}
			puts $log_csv_file_handle ""
		}
		close $log_csv_file_handle
		set stop_message "wrote data to $log_csv_file_name."
		puts $stop_message
		puts "directory: $directory  file_name: $log_csv_file_name"
		puts "::scc_util::extrac_to_csv $directory  $log_csv_file_name"
				
		set trace_csv_file_name  [format %s%s [file rootname $file_name] "_trace.psg.csv"]
		set trace_csv_file_handle [open $trace_csv_file_name "w"]
		
		set header "#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2"
		puts $trace_csv_file_handle $header
		foreach line $::psg::bufferAccessTrace {
			puts $trace_csv_file_handle $line
		}
		close $trace_csv_file_handle
		
		puts "directory: $directory  file_name: $trace_csv_file_name"
		puts "::scc_util::extrac_to_csv $directory  $trace_csv_file_name"
	}
}
