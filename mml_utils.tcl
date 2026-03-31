namespace eval ::mml_util {
	# ------------------------------------------------------
	#  Table for converting from PSG register value to Tone
	# ------------------------------------------------------
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
	dict set reg2tone	960	    o2a+
	dict set reg2tone	906	    o2b
	dict set reg2tone	855	    o3c
	dict set reg2tone	807	    o3c+
	dict set reg2tone	762	    o3d
	dict set reg2tone	719	    o3d+
	dict set reg2tone	679	    o3e
	dict set reg2tone	641	    o3f
	dict set reg2tone	605	    o3f+
	dict set reg2tone	571	    o3g
	dict set reg2tone	539	    o3g+
	dict set reg2tone	509	    o3a
	dict set reg2tone	480	    o3a+
	dict set reg2tone	453	    o3b
	dict set reg2tone	428	    o4c
	dict set reg2tone	404	    o4c+
	dict set reg2tone	381	    o4d
	dict set reg2tone	360	    o4d+
	dict set reg2tone	339	    o4e
	dict set reg2tone	320	    o4f
	dict set reg2tone	302	    o4f+
	dict set reg2tone	285	    o4g
	dict set reg2tone	269	    o4g+
	dict set reg2tone	254	    o4a
	dict set reg2tone	240	    o4a+
	dict set reg2tone	227	    o4b
	dict set reg2tone	214	    o5c
	dict set reg2tone	202	    o5c+
	dict set reg2tone	190	    o5d
	dict set reg2tone	180	    o5d+
	dict set reg2tone	170	    o5e
	dict set reg2tone	160	    o5f
	dict set reg2tone	151	    o5f+
	dict set reg2tone	143	    o5g
	dict set reg2tone	135	    o5g+
	dict set reg2tone	127	    o5a
	dict set reg2tone	120	    o5a+
	dict set reg2tone	113	    o5b
	dict set reg2tone	107	    o6c
	dict set reg2tone	101	    o6c+
	dict set reg2tone	95	    o6d
	dict set reg2tone	90	    o6d+
	dict set reg2tone	85	    o6e
	dict set reg2tone	80	    o6f
	dict set reg2tone	76	    o6f+
	dict set reg2tone	71	    o6g
	dict set reg2tone	67	    o6g+
	dict set reg2tone	64	    o6a
	dict set reg2tone	60	    o6a+
	dict set reg2tone	57	    o6b
	dict set reg2tone	53	    o7c
	dict set reg2tone	50	    o7c+
	dict set reg2tone	48	    o7d
	dict set reg2tone	45	    o7d+
	dict set reg2tone	42	    o7e
	dict set reg2tone	40	    o7f
	dict set reg2tone	38	    o7f+
	dict set reg2tone	36	    o7g
	dict set reg2tone	34	    o7g+
	dict set reg2tone	32	    o7a
	dict set reg2tone	30	    o7a+
	dict set reg2tone	28	    o7b
	dict set reg2tone	27	    o8c
	dict set reg2tone	25	    o8c+
	dict set reg2tone	24	    o8d
	dict set reg2tone	22	    o8d+
	dict set reg2tone	21	    o8e
	dict set reg2tone	20	    o8f
	dict set reg2tone	19	    o8f+
	dict set reg2tone	18	    o8g
	dict set reg2tone	17	    o8g+
	dict set reg2tone	16	    o8a
	dict set reg2tone	15	    o8a+
	dict set reg2tone	14	    o8b
	dict set reg2tone	0	    rest

	# Create the key list of 'reg2tone' table 
	set key_list [dict keys $reg2tone]
	
	# Get the tones pulled from a table using register values
	proc get_tone { reg } {
		set tone ""
		if {$reg == 0} {
			# If the register value is "0", it will return "rest"
			return r
		} elseif {[dict exist $::mml_util::reg2tone $reg] } {
			# If the value exists in the table as key, return the associated tone.
			set tone [dict get $::mml_util::reg2tone $reg]
			#return [string range $tone 2 end]
			return $tone
		} else {
			# If the value does not exist as a key, return the tone of the nearest higher key
			set key_stamp 3421
			foreach key $::mml_util::key_list {
				if { $key > $reg } {
					set key_stamp $key
				} else {
					set delta [expr $key_stamp - $reg]
					set tone [format "%s" [dict get $::mml_util::reg2tone $key_stamp]]
					break
				}
			}
		}
		return $tone
	}

	# Get the difference of the frequences between the register value and the correspond key
	proc get_delta { reg } {
		set delta 0
		if {[dict exist $::mml_util::reg2tone $reg] } {
			return $delta
		} else {
			set key_stamp 3421
			foreach key $::mml_util::key_list {
				if { $key > $reg } {
					set key_stamp $key
				} else {
					set delta [expr $key_stamp - $reg]
					break
				}
			}
		}
		return $delta
	}
	
	# Get the octave pulled from a table using register values
	proc get_octave { reg } {
		set tone [::mml_util::get_tone $reg]
		puts "get_octave tone:$tone"
		if {$tone == "r" } {
			return 1
		} else {
			puts "get_octave tone:$tone"
			return [string range $tone 1 1]
		}
	}
	
	# Get the scale pulled from a table using register values
	proc get_scale { reg } {
		set tone [::mml_util::get_tone $reg]
			if {$tone == "r" } {
				return r
			} else {
			# Regular expression
			set pattern {o[0-9]+([a-z+]+)}

			# Extract the string that follows the number
			if {[regexp $pattern $tone match result]} {
				puts "get_scale tone:$tone result:$result"
				return $result
			} else {
				puts "No match found"
				return r
			}
		}
	}
	
	# Get the calculated frequency from the register value
	# If the value of the register is 0, the highest value (111860.78125 for AY-3-8910) is returned.
	proc getToneFreqency {reg} {
		if { $reg == 0} { return [expr int(111860.78125)] }
		return [expr int(111860.78125/$reg)]
	}
	
	proc frequencyToMidiNote {freq} {
		# MIDIノート番号の計算式
		set midiNote [expr round(69 + 12 * log($freq / 440.0) / log(2))]
		return $midiNote
	}
}