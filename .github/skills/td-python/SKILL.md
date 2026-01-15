# TouchDesigner Python Coding Skill

This skill defines best practices for writing Python code within TouchDesigner projects.

## Documentation Reference

- **TouchDesigner Python Reference**: https://derivative.ca/UserGuide/Python
- **TouchDesigner Python Classes and Modules**: https://derivative.ca/UserGuide/Python_Classes_and_Modules
- **TouchDesigner Python Classes and Modules (list)**: https://docs.derivative.ca/Category:Python_Reference
- **TouchDesigner Python Tips**: https://derivative.ca/UserGuide/Python_Tips
- **TouchDesigner Info Categories**: https://docs.derivative.ca/Special:Categories
- **TouchDesigner Wiki**: https://docs.derivative.ca/
- **Operators Documentation**: https://derivative.ca/UserGuide/Operator
  - **OP Class Reference** (All operators extend this base class): https://docs.derivative.ca/OP_Class
  - **TOPs Documentation**: https://derivative.ca/UserGuide/TOP
    - https://derivative.ca/UserGuide/TOP_Class
  - **CHOPs Documentation**: https://derivative.ca/UserGuide/CHOP
    - https://derivative.ca/UserGuide/CHOP_Class
  - **POPs Documentation**: https://derivative.ca/UserGuide/POP
    - https://derivative.ca/UserGuide/POP_Class
  - **SOPs Documentation**: https://derivative.ca/UserGuide/SOP
    - https://derivative.ca/UserGuide/SOP_Class
  - **DATs Documentation**: https://derivative.ca/UserGuide/DAT
    - https://derivative.ca/UserGuide/DAT_Class
  - **MATs Documentation**: https://derivative.ca/UserGuide/MAT
    - https://derivative.ca/UserGuide/MAT_Class
- **COMP Class Reference**: https://docs.derivative.ca/COMP_Class
- **Base_COMP Class Reference** (Paired with python extensions, these are the OOP building blocks of TD apps): https://docs.derivative.ca/Base_COMP
- **TD Module Reference**: https://docs.derivative.ca/Td_Module

## Environment Context

TouchDesigner embeds a Python interpreter with built-in global objects and modules:

### Global TouchDesigner Objects (Always Available)
- `op` - Function to reference operators by path: `op('/project1/my_comp')`
- `ops` - Function to reference multiple operators: `ops('/project1/*')`
- `parent` - Reference to parent components: `parent()`, `parent(2)`
- `me` - Reference to the current operator running the script
- `root` - Reference to the root `/` operator
- `project` - Reference to the project settings and metadata
- `ui` - Reference to the UI state and dialogs
- `sysinfo` - System information
- `mod` - Module-on-demand for importing external `.py` files
- `ext` - Access extensions on components
- `run` - Execute code with delay: `run("print('hi')", delayFrames=60)`
- `absTime` - Absolute time since TouchDesigner started
- `app` - Application-level settings and info

### TouchDesigner Module (`td`)
```python
import td

td.project.folder      # Project directory path
td.project.name        # Project filename
td.absTime.frame       # Current absolute frame
td.absTime.seconds     # Current absolute time in seconds
```

## Global objects in custom python applications

- `op.App` - Reference to the main application component/extension
- `op.AppStore` - Reference to the application state storage component/extension

## Type Hints

All code **must** use Python type hints for clarity and IDE support. TouchDesigner provides stub types via `td` module.

- Using the `op()` or `ops()` functions will return the appropriate TD types (e.g., OP, COMP, DAT, TOP, CHOP, SOP, MAT, baseCOMP, etc.), However, we want to be specific with the sub-types when possible for better clarity and IDE support. There is a list of common TD types below.

### CHOP Types

[Ableton Link](https://derivative.ca/UserGuide/Ableton_Link_CHOP) | [Analyze](https://derivative.ca/UserGuide/Analyze_CHOP) | [Angle](https://derivative.ca/UserGuide/Angle_CHOP) | [Attribute](https://derivative.ca/UserGuide/Attribute_CHOP) | [Audio Band EQ](https://derivative.ca/UserGuide/Audio_Band_EQ_CHOP) | [Audio Binaural](https://derivative.ca/UserGuide/Audio_Binaural_CHOP) | [Audio Device In](https://derivative.ca/UserGuide/Audio_Device_In_CHOP) | [Audio Device Out](https://derivative.ca/UserGuide/Audio_Device_Out_CHOP) | [Audio Dynamics](https://derivative.ca/UserGuide/Audio_Dynamics_CHOP) | [Audio File In](https://derivative.ca/UserGuide/Audio_File_In_CHOP) | [Audio File Out](https://derivative.ca/UserGuide/Audio_File_Out_CHOP) | [Audio Filter](https://derivative.ca/UserGuide/Audio_Filter_CHOP) | [Audio Movie](https://derivative.ca/UserGuide/Audio_Movie_CHOP) | [Audio NDI](https://derivative.ca/UserGuide/Audio_NDI_CHOP) | [Audio Oscillator](https://derivative.ca/UserGuide/Audio_Oscillator_CHOP) | [Audio Para EQ](https://derivative.ca/UserGuide/Audio_Para_EQ_CHOP) | [Audio Play](https://derivative.ca/UserGuide/Audio_Play_CHOP) | [Audio Render](https://derivative.ca/UserGuide/Audio_Render_CHOP) | [Audio Spectrum](https://derivative.ca/UserGuide/Audio_Spectrum_CHOP) | [Audio Stream In](https://derivative.ca/UserGuide/Audio_Stream_In_CHOP) | [Audio Stream Out](https://derivative.ca/UserGuide/Audio_Stream_Out_CHOP) | [Audio VST](https://derivative.ca/UserGuide/Audio_VST_CHOP) | [Audio Web Render](https://derivative.ca/UserGuide/Audio_Web_Render_CHOP) | [Beat](https://derivative.ca/UserGuide/Beat_CHOP) | [Bind](https://derivative.ca/UserGuide/Bind_CHOP) | [BlackTrax](https://derivative.ca/UserGuide/BlackTrax_CHOP) | [Blend](https://derivative.ca/UserGuide/Blend_CHOP) | [Blob Track](https://derivative.ca/UserGuide/Blob_Track_CHOP) | [Body Track](https://derivative.ca/UserGuide/Body_Track_CHOP) | [Bullet Solver](https://derivative.ca/UserGuide/Bullet_Solver_CHOP) | [CHOP](https://derivative.ca/UserGuide/CHOP) | [Clip Blender](https://derivative.ca/UserGuide/Clip_Blender_CHOP) | [Clip](https://derivative.ca/UserGuide/Clip_CHOP) | [Clock](https://derivative.ca/UserGuide/Clock_CHOP) | [Composite](https://derivative.ca/UserGuide/Composite_CHOP) | [Constant](https://derivative.ca/UserGuide/Constant_CHOP) | [Copy](https://derivative.ca/UserGuide/Copy_CHOP) | [Count](https://derivative.ca/UserGuide/Count_CHOP) | [CPlusPlus](https://derivative.ca/UserGuide/CPlusPlus_CHOP) | [Cross](https://derivative.ca/UserGuide/Cross_CHOP) | [Cycle](https://derivative.ca/UserGuide/Cycle_CHOP) | [DAT to](https://derivative.ca/UserGuide/DAT_to_CHOP) | [Delay](https://derivative.ca/UserGuide/Delay_CHOP) | [Delete](https://derivative.ca/UserGuide/Delete_CHOP) | [DMX In](https://derivative.ca/UserGuide/DMX_In_CHOP) | [DMX Out](https://derivative.ca/UserGuide/DMX_Out_CHOP) | [Envelope](https://derivative.ca/UserGuide/Envelope_CHOP) | [EtherDream](https://derivative.ca/UserGuide/EtherDream_CHOP) | [Event](https://derivative.ca/UserGuide/Event_CHOP) | [Expression](https://derivative.ca/UserGuide/Expression_CHOP) | [Extend](https://derivative.ca/UserGuide/Extend_CHOP) | [Face Track](https://derivative.ca/UserGuide/Face_Track_CHOP) | [Fan](https://derivative.ca/UserGuide/Fan_CHOP) | [Feedback](https://derivative.ca/UserGuide/Feedback_CHOP) | [File In](https://derivative.ca/UserGuide/File_In_CHOP) | [File Out](https://derivative.ca/UserGuide/File_Out_CHOP) | [Filter](https://derivative.ca/UserGuide/Filter_CHOP) | [FreeD In](https://derivative.ca/UserGuide/FreeD_In_CHOP) | [FreeD Out](https://derivative.ca/UserGuide/FreeD_Out_CHOP) | [Function](https://derivative.ca/UserGuide/Function_CHOP) | [Gesture](https://derivative.ca/UserGuide/Gesture_CHOP) | [Handle](https://derivative.ca/UserGuide/Handle_CHOP) | [Helios DAC](https://derivative.ca/UserGuide/Helios_DAC_CHOP) | [Hog](https://derivative.ca/UserGuide/Hog_CHOP) | [Hokuyo](https://derivative.ca/UserGuide/Hokuyo_CHOP) | [Hold](https://derivative.ca/UserGuide/Hold_CHOP) | [Import Select](https://derivative.ca/UserGuide/Import_Select_CHOP) | [In](https://derivative.ca/UserGuide/In_CHOP) | [Info](https://derivative.ca/UserGuide/Info_CHOP) | [Interpolate](https://derivative.ca/UserGuide/Interpolate_CHOP) | [Introduction Tos Vid](https://derivative.ca/UserGuide/Introduction_To_CHOPs_Vid) | [Inverse Curve](https://derivative.ca/UserGuide/Inverse_Curve_CHOP) | [Inverse Kin](https://derivative.ca/UserGuide/Inverse_Kin_CHOP) | [Join](https://derivative.ca/UserGuide/Join_CHOP) | [Joystick](https://derivative.ca/UserGuide/Joystick_CHOP) | [Keyboard In](https://derivative.ca/UserGuide/Keyboard_In_CHOP) | [Keyframe](https://derivative.ca/UserGuide/Keyframe_CHOP) | [Kinect Azure](https://derivative.ca/UserGuide/Kinect_Azure_CHOP) | [Kinect](https://derivative.ca/UserGuide/Kinect_CHOP) | [Lag](https://derivative.ca/UserGuide/Lag_CHOP) | [Laser](https://derivative.ca/UserGuide/Laser_CHOP) | [Laser Device](https://derivative.ca/UserGuide/Laser_Device_CHOP) | [Leap Motion](https://derivative.ca/UserGuide/Leap_Motion_CHOP) | [Leuze ROD4](https://derivative.ca/UserGuide/Leuze_ROD4_CHOP) | [LFO](https://derivative.ca/UserGuide/LFO_CHOP) | [Limit](https://derivative.ca/UserGuide/Limit_CHOP) | [Logic](https://derivative.ca/UserGuide/Logic_CHOP) | [Lookup](https://derivative.ca/UserGuide/Lookup_CHOP) | [LTC In](https://derivative.ca/UserGuide/LTC_In_CHOP) | [LTC Out](https://derivative.ca/UserGuide/LTC_Out_CHOP) | [Math](https://derivative.ca/UserGuide/Math_CHOP) | [Merge](https://derivative.ca/UserGuide/Merge_CHOP) | [MIDI In](https://derivative.ca/UserGuide/MIDI_In_CHOP) | [MIDI In Map](https://derivative.ca/UserGuide/MIDI_In_Map_CHOP) | [MIDI Out](https://derivative.ca/UserGuide/MIDI_Out_CHOP) | [MoSys](https://derivative.ca/UserGuide/MoSys_CHOP) | [Mouse In](https://derivative.ca/UserGuide/Mouse_In_CHOP) | [Mouse Out](https://derivative.ca/UserGuide/Mouse_Out_CHOP) | [Ncam](https://derivative.ca/UserGuide/Ncam_CHOP) | [Noise](https://derivative.ca/UserGuide/Noise_CHOP) | [Null](https://derivative.ca/UserGuide/Null_CHOP) | [OAK Device](https://derivative.ca/UserGuide/OAK_Device_CHOP) | [OAK Select](https://derivative.ca/UserGuide/OAK_Select_CHOP) | [Object](https://derivative.ca/UserGuide/Object_CHOP) | [Oculus Audio](https://derivative.ca/UserGuide/Oculus_Audio_CHOP) | [Oculus Rift](https://derivative.ca/UserGuide/Oculus_Rift_CHOP) | [OpenVR](https://derivative.ca/UserGuide/OpenVR_CHOP) | [OptiTrack In](https://derivative.ca/UserGuide/OptiTrack_In_CHOP) | [OSC In](https://derivative.ca/UserGuide/OSC_In_CHOP) | [OSC Out](https://derivative.ca/UserGuide/OSC_Out_CHOP) | [Out](https://derivative.ca/UserGuide/Out_CHOP) | [Override](https://derivative.ca/UserGuide/Override_CHOP) | [Pan Tilt](https://derivative.ca/UserGuide/Pan_Tilt_CHOP) | [Panel](https://derivative.ca/UserGuide/Panel_CHOP) | [Pangolin](https://derivative.ca/UserGuide/Pangolin_CHOP) | [Parameter](https://derivative.ca/UserGuide/Parameter_CHOP) | [Pattern](https://derivative.ca/UserGuide/Pattern_CHOP) | [Perform](https://derivative.ca/UserGuide/Perform_CHOP) | [Phaser](https://derivative.ca/UserGuide/Phaser_CHOP) | [Pipe In](https://derivative.ca/UserGuide/Pipe_In_CHOP) | [Pipe Out](https://derivative.ca/UserGuide/Pipe_Out_CHOP) | [POP to](https://derivative.ca/UserGuide/POP_to_CHOP) | [PosiStageNet](https://derivative.ca/UserGuide/PosiStageNet_CHOP) | [Pulse](https://derivative.ca/UserGuide/Pulse_CHOP) | [RealSense](https://derivative.ca/UserGuide/RealSense_CHOP) | [Record](https://derivative.ca/UserGuide/Record_CHOP) | [Rename](https://derivative.ca/UserGuide/Rename_CHOP) | [Render Pick](https://derivative.ca/UserGuide/Render_Pick_CHOP) | [RenderStream In](https://derivative.ca/UserGuide/RenderStream_In_CHOP) | [Reorder](https://derivative.ca/UserGuide/Reorder_CHOP) | [Replace](https://derivative.ca/UserGuide/Replace_CHOP) | [Resample](https://derivative.ca/UserGuide/Resample_CHOP) | [S Curve](https://derivative.ca/UserGuide/S_Curve_CHOP) | [Scan](https://derivative.ca/UserGuide/Scan_CHOP) | [Script](https://derivative.ca/UserGuide/Script_CHOP) | [Select](https://derivative.ca/UserGuide/Select_CHOP) | [Sequencer](https://derivative.ca/UserGuide/Sequencer_CHOP) | [Serial](https://derivative.ca/UserGuide/Serial_CHOP) | [Shared Mem In](https://derivative.ca/UserGuide/Shared_Mem_In_CHOP) | [Shared Mem Out](https://derivative.ca/UserGuide/Shared_Mem_Out_CHOP) | [Shift](https://derivative.ca/UserGuide/Shift_CHOP) | [Shuffle](https://derivative.ca/UserGuide/Shuffle_CHOP) | [Slope](https://derivative.ca/UserGuide/Slope_CHOP) | [SOP to](https://derivative.ca/UserGuide/SOP_to_CHOP) | [Sort](https://derivative.ca/UserGuide/Sort_CHOP) | [Speed](https://derivative.ca/UserGuide/Speed_CHOP) | [Splice](https://derivative.ca/UserGuide/Splice_CHOP) | [Spring](https://derivative.ca/UserGuide/Spring_CHOP) | [ST2110 Device](https://derivative.ca/UserGuide/ST2110_Device_CHOP) | [Stretch](https://derivative.ca/UserGuide/Stretch_CHOP) | [Stype In](https://derivative.ca/UserGuide/Stype_In_CHOP) | [Stype Out](https://derivative.ca/UserGuide/Stype_Out_CHOP) | [Switch](https://derivative.ca/UserGuide/Switch_CHOP) | [Sync In](https://derivative.ca/UserGuide/Sync_In_CHOP) | [Sync Out](https://derivative.ca/UserGuide/Sync_Out_CHOP) | [Tablet](https://derivative.ca/UserGuide/Tablet_CHOP) | [Time Slice](https://derivative.ca/UserGuide/Time_Slice_CHOP) | [Timecode](https://derivative.ca/UserGuide/Timecode_CHOP) | [Timeline](https://derivative.ca/UserGuide/Timeline_CHOP) | [Timer](https://derivative.ca/UserGuide/Timer_CHOP) | [TOP to](https://derivative.ca/UserGuide/TOP_to_CHOP) | [Touch In](https://derivative.ca/UserGuide/Touch_In_CHOP) | [Touch Out](https://derivative.ca/UserGuide/Touch_Out_CHOP) | [Trail](https://derivative.ca/UserGuide/Trail_CHOP) | [Transform](https://derivative.ca/UserGuide/Transform_CHOP) | [Transform XYZ](https://derivative.ca/UserGuide/Transform_XYZ_CHOP) | [Trigger](https://derivative.ca/UserGuide/Trigger_CHOP) | [Trim](https://derivative.ca/UserGuide/Trim_CHOP) | [Warp](https://derivative.ca/UserGuide/Warp_CHOP) | [Wave](https://derivative.ca/UserGuide/Wave_CHOP) | [WrnchAI](https://derivative.ca/UserGuide/WrnchAI_CHOP) | [ZED](https://derivative.ca/UserGuide/ZED_CHOP) 

### DAT Types

[Art-Net](https://docs.derivative.ca/Art-Net_DAT) | [Audio Devices](https://docs.derivative.ca/Audio_Devices_DAT) | [CHOP Execute](https://docs.derivative.ca/CHOP_Execute_DAT) | [CHOP to](https://docs.derivative.ca/CHOP_to_DAT) | [Clip](https://docs.derivative.ca/Clip_DAT) | [Convert](https://docs.derivative.ca/Convert_DAT) | [CPlusPlus](https://docs.derivative.ca/CPlusPlus_DAT) | [DAT](https://docs.derivative.ca/DAT) | [DAT Execute](https://docs.derivative.ca/DAT_Execute_DAT) | [DAT Export](https://docs.derivative.ca/DAT_Export) | [Error](https://docs.derivative.ca/Error_DAT) | [EtherDream](https://docs.derivative.ca/EtherDream_DAT) | [Evaluate](https://docs.derivative.ca/Evaluate_DAT) | [Examine](https://docs.derivative.ca/Examine_DAT) | [Execute](https://docs.derivative.ca/Execute_DAT) | [FIFO](https://docs.derivative.ca/FIFO_DAT) | [File In](https://docs.derivative.ca/File_In_DAT) | [File Out](https://docs.derivative.ca/File_Out_DAT) | [Folder](https://docs.derivative.ca/Folder_DAT) | [In](https://docs.derivative.ca/In_DAT) | [Indices](https://docs.derivative.ca/Indices_DAT) | [Info](https://docs.derivative.ca/Info_DAT) | [Insert](https://docs.derivative.ca/Insert_DAT) | [JSON](https://docs.derivative.ca/JSON_DAT) | [Keyboard In](https://docs.derivative.ca/Keyboard_In_DAT) | [Lookup](https://docs.derivative.ca/Lookup_DAT) | [Media File Info](https://docs.derivative.ca/Media_File_Info_DAT) | [Merge](https://docs.derivative.ca/Merge_DAT) | [MIDI Event](https://docs.derivative.ca/MIDI_Event_DAT) | [MIDI In](https://docs.derivative.ca/MIDI_In_DAT) | [Monitors](https://docs.derivative.ca/Monitors_DAT) | [MPCDI](https://docs.derivative.ca/MPCDI_DAT) | [MQTT Client](https://docs.derivative.ca/MQTT_Client_DAT) | [Multi Touch In](https://docs.derivative.ca/Multi_Touch_In_DAT) | [NDI](https://docs.derivative.ca/NDI_DAT) | [Null](https://docs.derivative.ca/Null_DAT) | [OP Execute](https://docs.derivative.ca/OP_Execute_DAT) | [OP Find](https://docs.derivative.ca/OP_Find_DAT) | [OSC In](https://docs.derivative.ca/OSC_In_DAT) | [OSC Out](https://docs.derivative.ca/OSC_Out_DAT) | [Out](https://docs.derivative.ca/Out_DAT) | [Panel Execute](https://docs.derivative.ca/Panel_Execute_DAT) | [Parameter](https://docs.derivative.ca/Parameter_DAT) | [Parameter Execute](https://docs.derivative.ca/Parameter_Execute_DAT) | [ParGroup Execute](https://docs.derivative.ca/ParGroup_Execute_DAT) | [Perform](https://docs.derivative.ca/Perform_DAT) | [POP to](https://docs.derivative.ca/POP_to_DAT) | [Render Pick](https://docs.derivative.ca/Render_Pick_DAT) | [Reorder](https://docs.derivative.ca/Reorder_DAT) | [Script](https://docs.derivative.ca/Script_DAT) | [Select](https://docs.derivative.ca/Select_DAT) | [Serial](https://docs.derivative.ca/Serial_DAT) | [Serial Devices](https://docs.derivative.ca/Serial_Devices_DAT) | [SocketIO](https://docs.derivative.ca/SocketIO_DAT) | [SOP to](https://docs.derivative.ca/SOP_to_DAT) | [Sort](https://docs.derivative.ca/Sort_DAT) | [Substitute](https://docs.derivative.ca/Substitute_DAT) | [Switch](https://docs.derivative.ca/Switch_DAT) | [Table](https://docs.derivative.ca/Table_DAT) | [TCP/IP](https://docs.derivative.ca/TCP/IP_DAT) | [Text](https://docs.derivative.ca/Text_DAT) | [Touch In](https://docs.derivative.ca/Touch_In_DAT) | [Touch Out](https://docs.derivative.ca/Touch_Out_DAT) | [Transpose](https://docs.derivative.ca/Transpose_DAT) | [TUIO In](https://docs.derivative.ca/TUIO_In_DAT) | [UDP In](https://docs.derivative.ca/UDP_In_DAT) | [UDP Out](https://docs.derivative.ca/UDP_Out_DAT) | [UDT In](https://docs.derivative.ca/UDT_In_DAT) | [UDT Out](https://docs.derivative.ca/UDT_Out_DAT) | [Video Devices](https://docs.derivative.ca/Video_Devices_DAT) | [Web Client](https://docs.derivative.ca/Web_Client_DAT) | [Web](https://docs.derivative.ca/Web_DAT) | [Web Server](https://docs.derivative.ca/Web_Server_DAT) | [WebRTC](https://docs.derivative.ca/WebRTC_DAT) | [WebSocket](https://docs.derivative.ca/WebSocket_DAT) | [XML](https://docs.derivative.ca/XML_DAT)

### POP Types

[Accumulate](https://derivative.ca/UserGuide/Accumulate_POP) | [Alembic In](https://derivative.ca/UserGuide/Alembic_In_POP) | [Analyze](https://derivative.ca/UserGuide/Analyze_POP) | [Attribute Combine](https://derivative.ca/UserGuide/Attribute_Combine_POP) | [Attribute Convert](https://derivative.ca/UserGuide/Attribute_Convert_POP) | [Attribute](https://derivative.ca/UserGuide/Attribute_POP) | [Blend](https://derivative.ca/UserGuide/Blend_POP) | [Box](https://derivative.ca/UserGuide/Box_POP) | [Cache Blend](https://derivative.ca/UserGuide/Cache_Blend_POP) | [Cache](https://derivative.ca/UserGuide/Cache_POP) | [Cache Select](https://derivative.ca/UserGuide/Cache_Select_POP) | [CHOP to](https://derivative.ca/UserGuide/CHOP_to_POP) | [Circle](https://derivative.ca/UserGuide/Circle_POP) | [Connectivity](https://derivative.ca/UserGuide/Connectivity_POP) | [Convert](https://derivative.ca/UserGuide/Convert_POP) | [Copy](https://derivative.ca/UserGuide/Copy_POP) | [CPlusPlus](https://derivative.ca/UserGuide/CPlusPlus_POP) | [Curve](https://derivative.ca/UserGuide/Curve_POP) | [DAT to](https://derivative.ca/UserGuide/DAT_to_POP) | [Delete](https://derivative.ca/UserGuide/Delete_POP) | [Dimension](https://derivative.ca/UserGuide/Dimension_POP) | [DMX Fixture](https://derivative.ca/UserGuide/DMX_Fixture_POP) | [DMX Out](https://derivative.ca/UserGuide/DMX_Out_POP) | [Extrude](https://derivative.ca/UserGuide/Extrude_POP) | [Facet](https://derivative.ca/UserGuide/Facet_POP) | [Feedback](https://derivative.ca/UserGuide/Feedback_POP) | [Field](https://derivative.ca/UserGuide/Field_POP) | [File In](https://derivative.ca/UserGuide/File_In_POP) | [File Out](https://derivative.ca/UserGuide/File_Out_POP) | [Force Radial](https://derivative.ca/UserGuide/Force_Radial_POP) | [GLSL Advanced](https://derivative.ca/UserGuide/GLSL_Advanced_POP) | [GLSL Copy](https://derivative.ca/UserGuide/GLSL_Copy_POP) | [GLSL Create](https://derivative.ca/UserGuide/GLSL_Create_POP) | [GLSL](https://derivative.ca/UserGuide/GLSL_POP) | [GLSL Select](https://derivative.ca/UserGuide/GLSL_Select_POP) | [Grid](https://derivative.ca/UserGuide/Grid_POP) | [Group](https://derivative.ca/UserGuide/Group_POP) | [Histogram](https://derivative.ca/UserGuide/Histogram_POP) | [Import Select](https://derivative.ca/UserGuide/Import_Select_POP) | [In](https://derivative.ca/UserGuide/In_POP) | [Limit](https://derivative.ca/UserGuide/Limit_POP) | [Line Break](https://derivative.ca/UserGuide/Line_Break_POP) | [Line Divide](https://derivative.ca/UserGuide/Line_Divide_POP) | [Line Metrics](https://derivative.ca/UserGuide/Line_Metrics_POP) | [Line](https://derivative.ca/UserGuide/Line_POP) | [Line Resample](https://derivative.ca/UserGuide/Line_Resample_POP) | [Line Smooth](https://derivative.ca/UserGuide/Line_Smooth_POP) | [Line Thick](https://derivative.ca/UserGuide/Line_Thick_POP) | [Lookup Attribute](https://derivative.ca/UserGuide/Lookup_Attribute_POP) | [Lookup Channel](https://derivative.ca/UserGuide/Lookup_Channel_POP) | [Lookup Texture](https://derivative.ca/UserGuide/Lookup_Texture_POP) | [Math Combine](https://derivative.ca/UserGuide/Math_Combine_POP) | [Math Mix](https://derivative.ca/UserGuide/Math_Mix_POP) | [Math](https://derivative.ca/UserGuide/Math_POP) | [Merge](https://derivative.ca/UserGuide/Merge_POP) | [Neighbor](https://derivative.ca/UserGuide/Neighbor_POP) | [Noise](https://derivative.ca/UserGuide/Noise_POP) | [Normal](https://derivative.ca/UserGuide/Normal_POP) | [Normalize](https://derivative.ca/UserGuide/Normalize_POP) | [Null](https://derivative.ca/UserGuide/Null_POP) | [OAK Select](https://derivative.ca/UserGuide/OAK_Select_POP) | [Out](https://derivative.ca/UserGuide/Out_POP) | [Particle](https://derivative.ca/UserGuide/Particle_POP) | [Pattern](https://derivative.ca/UserGuide/Pattern_POP) | [Phaser](https://derivative.ca/UserGuide/Phaser_POP) | [Plane](https://derivative.ca/UserGuide/Plane_POP) | [Point File In](https://derivative.ca/UserGuide/Point_File_In_POP) | [Point Generator](https://derivative.ca/UserGuide/Point_Generator_POP) | [Point](https://derivative.ca/UserGuide/Point_POP) | [Points, Vertices and Primitives ins](https://derivative.ca/UserGuide/Points,_Vertices_and_Primitives_in_POPs) | [Polygonize](https://derivative.ca/UserGuide/Polygonize_POP) | [POP](https://derivative.ca/UserGuide/POP) | [Primitive](https://derivative.ca/UserGuide/Primitive_POP) | [Projection](https://derivative.ca/UserGuide/Projection_POP) | [Proximity](https://derivative.ca/UserGuide/Proximity_POP) | [Quantize](https://derivative.ca/UserGuide/Quantize_POP) | [Random](https://derivative.ca/UserGuide/Random_POP) | [Ray](https://derivative.ca/UserGuide/Ray_POP) | [Rectangle](https://derivative.ca/UserGuide/Rectangle_POP) | [ReRange](https://derivative.ca/UserGuide/ReRange_POP) | [Revolve](https://derivative.ca/UserGuide/Revolve_POP) | [Select](https://derivative.ca/UserGuide/Select_POP) | [Skin Deform](https://derivative.ca/UserGuide/Skin_Deform_POP) | [Skin](https://derivative.ca/UserGuide/Skin_POP) | [SOP to](https://derivative.ca/UserGuide/SOP_to_POP) | [Sort](https://derivative.ca/UserGuide/Sort_POP) | [Sphere](https://derivative.ca/UserGuide/Sphere_POP) | [Sprinkle](https://derivative.ca/UserGuide/Sprinkle_POP) | [Subdivide](https://derivative.ca/UserGuide/Subdivide_POP) | [Switch](https://derivative.ca/UserGuide/Switch_POP) | [Texture Map](https://derivative.ca/UserGuide/Texture_Map_POP) | [TOP to](https://derivative.ca/UserGuide/TOP_to_POP) | [Topology](https://derivative.ca/UserGuide/Topology_POP) | [Torus](https://derivative.ca/UserGuide/Torus_POP) | [Trail](https://derivative.ca/UserGuide/Trail_POP) | [Transform](https://derivative.ca/UserGuide/Transform_POP) | [Trig](https://derivative.ca/UserGuide/Trig_POP) | [Tube](https://derivative.ca/UserGuide/Tube_POP) | [Twist](https://derivative.ca/UserGuide/Twist_POP) | [ZED](https://derivative.ca/UserGuide/ZED_POP)

### TOP Types

[Add](https://derivative.ca/UserGuide/Add_TOP) | [Analyze](https://derivative.ca/UserGuide/Analyze_TOP) | [Anti Alias](https://derivative.ca/UserGuide/Anti_Alias_TOP) | [Blob Track](https://derivative.ca/UserGuide/Blob_Track_TOP) | [Bloom](https://derivative.ca/UserGuide/Bloom_TOP) | [Blur](https://derivative.ca/UserGuide/Blur_TOP) | [Cache Select](https://derivative.ca/UserGuide/Cache_Select_TOP) | [Cache](https://derivative.ca/UserGuide/Cache_TOP) | [Channel Mix](https://derivative.ca/UserGuide/Channel_Mix_TOP) | [CHOP to](https://derivative.ca/UserGuide/CHOP_to_TOP) | [Chroma Key](https://derivative.ca/UserGuide/Chroma_Key_TOP) | [Circle](https://derivative.ca/UserGuide/Circle_TOP) | [Composite](https://derivative.ca/UserGuide/Composite_TOP) | [Constant](https://derivative.ca/UserGuide/Constant_TOP) | [Convolve](https://derivative.ca/UserGuide/Convolve_TOP) | [Corner Pin](https://derivative.ca/UserGuide/Corner_Pin_TOP) | [CPlusPlus](https://derivative.ca/UserGuide/CPlusPlus_TOP) | [Crop](https://derivative.ca/UserGuide/Crop_TOP) | [Cross](https://derivative.ca/UserGuide/Cross_TOP) | [Cube Map](https://derivative.ca/UserGuide/Cube_Map_TOP) | [Depth](https://derivative.ca/UserGuide/Depth_TOP) | [Difference](https://derivative.ca/UserGuide/Difference_TOP) | [Direct Display Out](https://derivative.ca/UserGuide/Direct_Display_Out_TOP) | [DirectX In](https://derivative.ca/UserGuide/DirectX_In_TOP) | [DirectX Out](https://derivative.ca/UserGuide/DirectX_Out_TOP) | [Displace](https://derivative.ca/UserGuide/Displace_TOP) | [Edge](https://derivative.ca/UserGuide/Edge_TOP) | [Emboss](https://derivative.ca/UserGuide/Emboss_TOP) | [Feedback](https://derivative.ca/UserGuide/Feedback_TOP) | [Fit](https://derivative.ca/UserGuide/Fit_TOP) | [Flip](https://derivative.ca/UserGuide/Flip_TOP) | [Function](https://derivative.ca/UserGuide/Function_TOP) | [GLSL Multi](https://derivative.ca/UserGuide/GLSL_Multi_TOP) | [GLSL](https://derivative.ca/UserGuide/GLSL_TOP) | [HSV Adjust](https://derivative.ca/UserGuide/HSV_Adjust_TOP) | [HSV to RGB](https://derivative.ca/UserGuide/HSV_to_RGB_TOP) | [Import Select](https://derivative.ca/UserGuide/Import_Select_TOP) | [In](https://derivative.ca/UserGuide/In_TOP) | [Inside](https://derivative.ca/UserGuide/Inside_TOP) | [Kinect Azure Select](https://derivative.ca/UserGuide/Kinect_Azure_Select_TOP) | [Kinect Azure](https://derivative.ca/UserGuide/Kinect_Azure_TOP) | [Kinect](https://derivative.ca/UserGuide/Kinect_TOP) | [Layer Mix](https://derivative.ca/UserGuide/Layer_Mix_TOP) | [Layer](https://derivative.ca/UserGuide/Layer_TOP) | [Layout](https://derivative.ca/UserGuide/Layout_TOP) | [Leap Motion](https://derivative.ca/UserGuide/Leap_Motion_TOP) | [Lens Distort](https://derivative.ca/UserGuide/Lens_Distort_TOP) | [Level](https://derivative.ca/UserGuide/Level_TOP) | [Limit](https://derivative.ca/UserGuide/Limit_TOP) | [Lookup](https://derivative.ca/UserGuide/Lookup_TOP) | [Luma Blur](https://derivative.ca/UserGuide/Luma_Blur_TOP) | [Luma Level](https://derivative.ca/UserGuide/Luma_Level_TOP) | [Math](https://derivative.ca/UserGuide/Math_TOP) | [Matte](https://derivative.ca/UserGuide/Matte_TOP) | [Mirror](https://derivative.ca/UserGuide/Mirror_TOP) | [Monochrome](https://derivative.ca/UserGuide/Monochrome_TOP) | [MoSys](https://derivative.ca/UserGuide/MoSys_TOP) | [Movie File In](https://derivative.ca/UserGuide/Movie_File_In_TOP) | [Movie File Out](https://derivative.ca/UserGuide/Movie_File_Out_TOP) | [MPCDI](https://derivative.ca/UserGuide/MPCDI_TOP) | [Multiply](https://derivative.ca/UserGuide/Multiply_TOP) | [Ncam](https://derivative.ca/UserGuide/Ncam_TOP) | [NDI In](https://derivative.ca/UserGuide/NDI_In_TOP) | [NDI Out](https://derivative.ca/UserGuide/NDI_Out_TOP) | [Noise](https://derivative.ca/UserGuide/Noise_TOP) | [Normal Map](https://derivative.ca/UserGuide/Normal_Map_TOP) | [Notch](https://derivative.ca/UserGuide/Notch_TOP) | [Null](https://derivative.ca/UserGuide/Null_TOP) | [NVIDIA Background](https://derivative.ca/UserGuide/NVIDIA_Background_TOP) | [NVIDIA Denoise](https://derivative.ca/UserGuide/NVIDIA_Denoise_TOP) | [NVIDIA Flex](https://derivative.ca/UserGuide/NVIDIA_Flex_TOP) | [NVIDIA Flow](https://derivative.ca/UserGuide/NVIDIA_Flow_TOP) | [NVIDIA Upscaler](https://derivative.ca/UserGuide/NVIDIA_Upscaler_TOP) | [OAK Select](https://derivative.ca/UserGuide/OAK_Select_TOP) | [Oculus Rift](https://derivative.ca/UserGuide/Oculus_Rift_TOP) | [OP Viewer](https://derivative.ca/UserGuide/OP_Viewer_TOP) | [OpenColorIO](https://derivative.ca/UserGuide/OpenColorIO_TOP) | [OpenVR](https://derivative.ca/UserGuide/OpenVR_TOP) | [Optical Flow](https://derivative.ca/UserGuide/Optical_Flow_TOP) | [Orbbec Select](https://derivative.ca/UserGuide/Orbbec_Select_TOP) | [Orbbec](https://derivative.ca/UserGuide/Orbbec_TOP) | [Ouster Select](https://derivative.ca/UserGuide/Ouster_Select_TOP) | [Ouster](https://derivative.ca/UserGuide/Ouster_TOP) | [Out](https://derivative.ca/UserGuide/Out_TOP) | [Outside](https://derivative.ca/UserGuide/Outside_TOP) | [Over](https://derivative.ca/UserGuide/Over_TOP) | [Pack](https://derivative.ca/UserGuide/Pack_TOP) | [Photoshop In](https://derivative.ca/UserGuide/Photoshop_In_TOP) | [Point File In](https://derivative.ca/UserGuide/Point_File_In_TOP) | [Point File Select](https://derivative.ca/UserGuide/Point_File_Select_TOP) | [Point Transform](https://derivative.ca/UserGuide/Point_Transform_TOP) | [POP to](https://derivative.ca/UserGuide/POP_to_TOP) | [PreFilter Map](https://derivative.ca/UserGuide/PreFilter_Map_TOP) | [Projection](https://derivative.ca/UserGuide/Projection_TOP) | [Ramp](https://derivative.ca/UserGuide/Ramp_TOP) | [RealSense](https://derivative.ca/UserGuide/RealSense_TOP) | [Rectangle](https://derivative.ca/UserGuide/Rectangle_TOP) | [Remap](https://derivative.ca/UserGuide/Remap_TOP) | [Render Pass](https://derivative.ca/UserGuide/Render_Pass_TOP) | [Render Select](https://derivative.ca/UserGuide/Render_Select_TOP) | [Render Simple](https://derivative.ca/UserGuide/Render_Simple_TOP) | [Render](https://derivative.ca/UserGuide/Render_TOP) | [RenderStream In](https://derivative.ca/UserGuide/RenderStream_In_TOP) | [RenderStream Out](https://derivative.ca/UserGuide/RenderStream_Out_TOP) | [Reorder](https://derivative.ca/UserGuide/Reorder_TOP) | [Resolution](https://derivative.ca/UserGuide/Resolution_TOP) | [RGB Key](https://derivative.ca/UserGuide/RGB_Key_TOP) | [RGB to HSV](https://derivative.ca/UserGuide/RGB_to_HSV_TOP) | [Scalable Display](https://derivative.ca/UserGuide/Scalable_Display_TOP) | [Screen Grab](https://derivative.ca/UserGuide/Screen_Grab_TOP) | [Screen](https://derivative.ca/UserGuide/Screen_TOP) | [Script](https://derivative.ca/UserGuide/Script_TOP) | [Select](https://derivative.ca/UserGuide/Select_TOP) | [Shared Mem In](https://derivative.ca/UserGuide/Shared_Mem_In_TOP) | [Shared Mem Out](https://derivative.ca/UserGuide/Shared_Mem_Out_TOP) | [SICK](https://derivative.ca/UserGuide/SICK_TOP) | [Slope](https://derivative.ca/UserGuide/Slope_TOP) | [Spectrum](https://derivative.ca/UserGuide/Spectrum_TOP) | [SSAO](https://derivative.ca/UserGuide/SSAO_TOP) | [ST2110 In](https://derivative.ca/UserGuide/ST2110_In_TOP) | [ST2110 Out](https://derivative.ca/UserGuide/ST2110_Out_TOP) | [Stype](https://derivative.ca/UserGuide/Stype_TOP) | [Substance Select](https://derivative.ca/UserGuide/Substance_Select_TOP) | [Substance](https://derivative.ca/UserGuide/Substance_TOP) | [Subtract](https://derivative.ca/UserGuide/Subtract_TOP) | [SVG](https://derivative.ca/UserGuide/SVG_TOP) | [Switch](https://derivative.ca/UserGuide/Switch_TOP) | [Syphon Spout In](https://derivative.ca/UserGuide/Syphon_Spout_In_TOP) | [Syphon Spout Out](https://derivative.ca/UserGuide/Syphon_Spout_Out_TOP) | [Text](https://derivative.ca/UserGuide/Text_TOP) | [Texture 3D](https://derivative.ca/UserGuide/Texture_3D_TOP) | [Threshold](https://derivative.ca/UserGuide/Threshold_TOP) | [Tile](https://derivative.ca/UserGuide/Tile_TOP) | [Time Machine](https://derivative.ca/UserGuide/Time_Machine_TOP) | [Tone Map](https://derivative.ca/UserGuide/Tone_Map_TOP) | [TOP](https://derivative.ca/UserGuide/TOP) | [Touch In](https://derivative.ca/UserGuide/Touch_In_TOP) | [Touch Out](https://derivative.ca/UserGuide/Touch_Out_TOP) | [Transform](https://derivative.ca/UserGuide/Transform_TOP) | [Under](https://derivative.ca/UserGuide/Under_TOP) | [Video Device In](https://derivative.ca/UserGuide/Video_Device_In_TOP) | [Video Device Out](https://derivative.ca/UserGuide/Video_Device_Out_TOP) | [Video Stream In](https://derivative.ca/UserGuide/Video_Stream_In_TOP) | [Video Stream Out](https://derivative.ca/UserGuide/Video_Stream_Out_TOP) | [Vioso](https://derivative.ca/UserGuide/Vioso_TOP) | [Web Render](https://derivative.ca/UserGuide/Web_Render_TOP) | [ZED Select](https://derivative.ca/UserGuide/ZED_Select_TOP) | [ZED](https://derivative.ca/UserGuide/ZED_TOP)

### Common TouchDesigner Types
```python
from typing import Optional, Union, List

# Core TD types (available in TD's Python environment)
# OP, COMP, DAT, TOP, CHOP, SOP, MAT, baseCOMP, etc.

def get_operator(path: str) -> OP:
    """Get an operator by path."""
    return op(path)

def get_table_value(table: DAT, row: Union[int, str], col: Union[int, str]) -> Optional[str]:
    """Get a value from a table DAT."""
    cell = table[row, col]
    return cell.val if cell else None

def set_parameter(comp: COMP, param_name: str, value: Union[int, float, str, bool]) -> None:
    """Set a parameter on a component."""
    comp.par[param_name] = value
```

### Extension Class Pattern
```python
class MyExtension:
    """
    Extension class for a COMP.
    
    Extensions are attached to components and provide custom methods
    accessible via `op('/path').ExtensionName.Method()` or `op.ExtensionName.Method()`.
    """
    
    def __init__(self, ownerComp: COMP) -> None:
        self.ownerComp: COMP = ownerComp
    
    def GetValue(self, key: str) -> Optional[str]:
        """Get a value by key."""
        return None
    
    def SetValue(self, key: str, value: str) -> None:
        """Set a value by key."""
        pass
```

## Code Style Guidelines

### 1. Naming Conventions
- **Classes**: `PascalCase` - `class AppController:`
- **Extension Methods (public)**: `PascalCase` - `def GetCurrentState(self):`
- **Extension Methods (private)**: `camelCase` - `def getCurrentState(self):`
- **Utility Functions** (in util.py files): `snake_case` - `def get_table_value(table, key):`
- **Constants**: `UPPER_SNAKE_CASE` - `MODE_ATTRACT = 'attract'`
- **Private Methods**: : `camelCase`, no leading underscore

### 2. Indentation
- Use **tabs** for indentation (TouchDesigner convention)
- Align continuation lines appropriately

### 3. String Formatting
- Use **f-strings** for string interpolation:
```python
print(f"[{self.__class__.__name__}] Current state: {state}")
```

### 4. Logging Pattern
- Prefix logs with the class/module name in brackets:
```python
print(f"[App] Initializing...")
print(f"[TableUtil] Row not found: {key}")
```

### 5. Docstrings
- Use docstrings for all classes and public methods:
```python
def process_data(self, data: dict) -> bool:
    """
    Process incoming data and update state.
    
    Args:
        data: Dictionary containing the data to process
        
    Returns:
        True if processing succeeded, False otherwise
    """
    pass
```

## Common Patterns

### Operator References
```python
# By absolute path
my_op: OP = op('/project1/container1/my_op')

# By relative path (from current op)
child_op: OP = op('./child')
sibling_op: OP = op('../sibling')

# Using shortcut (defined in component)
app_store: AppStore = op.AppStore

# Parent references
parent_comp: COMP = parent()
grandparent: COMP = parent(2)
```

### Working with DAT Tables
```python
def get_kv_prop(table: DAT, key: str) -> Optional[str]:
    """Get a key-value property from a table."""
    row = table.row(key)
    if row is not None:
        return row[1].val
    return None

def set_kv_prop(table: DAT, key: str, value: str) -> None:
    """Set a key-value property in a table."""
    row = table.row(key)
    if row is not None:
        table.replaceRow(key, [key, value])
    else:
        table.appendRow([key, value])
```

### Working with Parameters
```python
def get_param(comp: COMP, name: str) -> any:
    """Get a parameter value."""
    return comp.par[name].eval()

def set_param(comp: COMP, name: str, value: any) -> None:
    """Set a parameter value."""
    comp.par[name] = value

def pulse_param(comp: COMP, name: str) -> None:
    """Pulse a parameter (for pulse-type params)."""
    comp.par[name].pulse()
```

### Delayed Execution
```python
# Execute after N frames
run("op('/project1/my_comp').DoSomething()", delayFrames=60)

# Execute after N seconds  
run("print('delayed')", delayMilliSeconds=1000)

# Execute with arguments (use f-string carefully)
value = 42
run(f"op('/project1/my_comp').ProcessValue({value})", delayFrames=1)
```

### Extension Communication
```python
# Call extension method on another component
op.AppStore.SetString('key', 'value')
result = op.Audio.GetVolume()

# Access extension from path
op('/project1/my_comp').ext.MyExtension.DoSomething()
```

## File Organization

### Directory Structure
```
touchdesigner/
├── project.toe           # Main TouchDesigner project file
└── python/
    ├── extensions/       # Extension classes (attached to COMPs)
    │   ├── App.py
    │   └── MyFeature.py
    ├── scripts/          # Standalone scripts
    │   └── requirements.txt
    └── util/             # Utility modules
        ├── __init__.py
        ├── table_util.py
        ├── file_util.py
        └── net/
```

### Externalizing Python Files
- Extension files are externalized to `python/extensions/`
- Utility modules are externalized to `python/util/`
- Use `mod.module_name` to import externalized modules:
```python
# Import externalized module
table_utils = mod.table_util
value = table_utils.get_kv_prop(table, 'my_key')
```

## Error Handling

```python
def safe_get_op(path: str) -> Optional[OP]:
    """Safely get an operator, returning None if not found."""
    try:
        result = op(path)
        if result is None:
            print(f"[Warning] Operator not found: {path}")
        return result
    except Exception as e:
        print(f"[Error] Failed to get operator {path}: {e}")
        return None
```

## Performance Considerations

1. **Cache operator references** - Don't call `op()` repeatedly in tight loops
2. **Use `cook` wisely** - Avoid forcing cooks unnecessarily
3. **Batch table operations** - Use `clear()` and rebuild vs many individual edits
4. **Minimize `run()` calls** - Prefer direct execution when possible
5. **Use `delayFrames` over `delayMilliSeconds`** for frame-accurate timing

## Anti-Patterns to Avoid

```python
# ❌ Don't use bare except
try:
    do_something()
except:
    pass

# ✅ Catch specific exceptions
try:
    do_something()
except ValueError as e:
    print(f"[Error] Invalid value: {e}")

# ❌ Don't repeat op() calls
for i in range(100):
    op('/project1/data').appendRow([i])

# ✅ Cache the reference
data_table = op('/project1/data')
for i in range(100):
    data_table.appendRow([i])

# ❌ Don't use magic strings repeatedly
if state == 'attract':
    pass

# ✅ Use constants
MODE_ATTRACT = 'attract'
if state == MODE_ATTRACT:
    pass
```

## Testing in TouchDesigner

- Use the **Textport** (Alt+T) for quick script testing
- Print debug info with class prefixes for easy filtering
- Use `debug()` for breakpoint-style debugging (opens Textport)

## IDE Setup (External Editing)

For external editing with type hints and autocomplete:
1. Point your IDE to TouchDesigner's Python: `C:\Program Files\Derivative\TouchDesigner\bin\python.exe`
2. Install TD stubs for autocomplete (if available)
3. Configure your IDE to use tabs for indentation
