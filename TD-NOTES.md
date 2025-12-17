# TouchDesigner Notes

* Docs  
  * [https://derivative.ca/UserGuide](https://derivative.ca/UserGuide)   
  * [https://derivative.ca/UserGuide/More\_Things\_to\_Know\_about\_TouchDesigner](https://derivative.ca/UserGuide/More_Things_to_Know_about_TouchDesigner)   
  * [https://derivative.ca/UserGuide/Project\_Class](https://derivative.ca/UserGuide/Project_Class)  
  * [https://derivative.ca/UserGuide/AbsTime\_Class](https://derivative.ca/UserGuide/AbsTime_Class)   
  * [https://derivative.ca/UserGuide/Performance\_Monitor](https://derivative.ca/UserGuide/Performance_Monitor)   
* Key commands:  
  * [https://derivative.ca/UserGuide/Application\_Shortcuts](https://derivative.ca/UserGuide/Application_Shortcuts)   
  * Network nav: I (in), U (up), H (home)  
  * TAB  
  * Parameter window: P to toggle  
  * Shift \+ C for a comment\!  
  * ALT \+ S for project search  
  * ALT \+ S for floating textport window  
* Python snips  
  * Set a node’s parameter:  
    **op(‘noise1’).par.period \= 1**  
  * Get a node’s parameter (numeric)  
    **op.par.Smoothrange.eval()**  
    **me.parent().par.Smoothrange.eval()**  
  * Get the first input of an op (useful when reading data)  
    **op.inputs\[0\]**  
  * Make a connection between nodes  
    **op.outputConnectors\[0\].connect(op2)**  
    Loop through replicants with index  
    **for i, c in enumerate(newOps):**  
  * Use the size of parent Container to scale a UI element  
    **me.parent.width()**  
  * run() w/delay from extension  
    **run("parent().SampleTriggerOff()", fromOP=me, delayFrames=1)**  
    **run(f"op('{self.ownerComp.path}').PulseTriggerLaunch()", delayFrames=delayFrames)**  
  * Call a python function in another dat:  
    **op(‘text\_other\_script’).module.function\_name()**  
* Parameter window  
  * hover, then click & hold to get different drag scales, then drag left/right while still holding  
  * click "I" for the node's info window  
  * click "?" for help info. 2nd "?" is python help  
  * ALT \+ mouse hover to get a parameter tip  
* Panes  
  * ALT \+ Z \- close pane w/mouse inside  
  * ALT \+ \[ or \] \- split cur pane  
* Locations (secret)  
  * /sys  
  * /ui  
  * /local/time  
* Operator menu  
  * Darker options are "generators"  
* Network tricks  
  * Select multiple items to change parameters on all  
  * ALT \+ N to add a null after the selected TOP  
* Create a BaseComp component  
  * Create multiple nodes, right-click network background, and do Collapse Selected, add null at the end for output  
  * Create Select node outside of the base component, split pane, and drag entire null TOP over to Select’s Parameter window as the source TOP  
  * Reuse the component by giving the node a name, opening the TD palette on the left, add a folder in My Components, then drag your BaseComp into the folder  
  * The Select top allows us to dynamically make connections when switching texture sources. We could also create an Out top, which would give our BaseComp an output connector  
* Create a Component/Extension w/Python script  
  * [https://derivative.ca/UserGuide/Extensions](https://derivative.ca/UserGuide/Extensions)   
  * Create a base Component, right-click and choose Customize Component to open the Component Editor  
  * In the Extensions dropdown, enter the name of the component and click add  
  * Add custom parameters that can be accessed inside the Base comp  
  * [https://interactiveimmersive.io/blog/deployment/large-scale-touchdesigner-projects/](https://interactiveimmersive.io/blog/deployment/large-scale-touchdesigner-projects/)   
* Right-click existing output connection will insert in between   
  * Middle click will create a new branch  
* Feedback  
  * Need to change Comp order  
* Compositing  
  * Constant TOP \- use this with rgba(0,0,0,0) to create a specific-sized FBO for compositing  
  * Order in composite TOPs like Over depend on the order of inputs  
  * Use multiple Over TOPs to add multiple graphics to a composite \- this lets you treat each new additional texture with its own parameters, which will probably be different from each other  
  * Blend modes:   
    * In Palette, “blendModes” example shows lots of blending previews  
    * In Composite TOP parameters, “Preview Grid” toggle will show all possible blend modes. If you see one split, that shows the result of different-ordered inputs  
* Interpolating numbers  
  * Lag & Filter CHOPs help with this. Lag has a time for up/down, and Filter uses the same for both  
* Data  
  * [TouchDesigner's Data Model - Tutorial](https://www.youtube.com/watch?v=Xvg8z_d6ZJU)  
* Expressions  
  * me.digits \- grabs the end number of your node  
* To kill a bunch of nodes, select all w/ctrl \+ a, right-click on empty space and “Collapse selected”, then click the ‘x’ on the Component node to turn off cooking  
* Facet SOP: Unique Points & 2nd Computer Normals to get low-poly lighting  
* self in Python  
  * [What is "self" in Python?](https://www.youtube.com/watch?v=oaiQ5hYKHTE)  
  * [How bound methods are the key to understanding SELF in Python.](https://www.youtube.com/watch?v=x4j6bzbbx2o)   
* Python paths  
  * C:\\Program Files\\Derivative\\TouchDesigner\\bin\\Lib\\site-packages  
    * System var path:   
      C:\\msys64\\ucrt64\\bin  
    * User var path  
      C:\\Users\\cacheflowe\\AppData\\Roaming\\Python\\Python311\\Scripts  
  * [Anaconda \- Managing Python Environments and 3rd-Party Libraries in TouchDesigner | Derivative](https://derivative.ca/community-post/tutorial/anaconda-managing-python-environments-and-3rd-party-libraries-touchdesigner)   
  * [How to use external python libraries in Touchdesigner](https://www.youtube.com/watch?v=_U5gcTEsupE)  
  * [External Python Libraries | Derivative](https://derivative.ca/community-post/tutorial/external-python-libraries/61022) \- Matt Ragan external python tutorials  
  * [https://derivative.ca/UserGuide/Category:Python](https://derivative.ca/UserGuide/Category:Python)   
  * [GeoPix V2 - Getting Started \#1 - Installation & Setup](https://www.youtube.com/watch?v=HEdTy6hLl4c)   
* Optimization/performance & larger projects  
  * [https://derivative.ca/UserGuide/Optimize](https://derivative.ca/UserGuide/Optimize)   
  * [The Ultimate Movie Loading Guide For TouchDesigner Projects](https://www.youtube.com/watch?v=EGrBcoH5fjc)  
  * [Easy Optimization Tricks in TouchDesigner - Tutorial](https://www.youtube.com/watch?v=3XniGOP4V0k)  
  * [Permanent Installation Autostart Scripts in TouchDesigner - Tutorial](https://www.youtube.com/watch?v=-djb6U-ntyY)  
  * [Best Practices for TouchDesigner Collaboration](https://www.youtube.com/watch?v=6KPwrmrBoAE)  
  * [1/3 TouchDesigner Vol.035 Cooking, Optimization, & SceneChanger](https://www.youtube.com/watch?v=JpTv_aZam-I) YESSS  
  * [Engine COMP in TouchDesigner - An Introduction](https://www.youtube.com/watch?v=Fau61Cz80iY)  
  * [Advanced Techniques in Media Management, Sequencing and Playback - Peter Sistrom](https://www.youtube.com/watch?v=ufwO61zEAzo)  
* Deeper tools to think about  
  * [https://github.com/mhammond/pywin32](https://github.com/mhammond/pywin32)  
  * [https://github.com/IntentDev/touchpy](https://github.com/IntentDev/touchpy)   
  * Svg tools  
* Shell script  
  * [TouchDesigner | Start-up Configuration with Environment Variables – Matthew Ragan](https://matthewragan.com/2019/08/05/touchdesigner-start-up-configuration-with-environment-variables/)   
* Threading  
  * [https://derivative.ca/UserGuide/Run\_Command\_Examples](https://derivative.ca/UserGuide/Run_Command_Examples) 

### Thoughts

Advantages

* Visualization of graphics operation chains (shaders, compositing, etc)  
* Instant UI for everything. You have to manually connect that in code  
* Real-time editing. Debug mode in Java gets us close, but nowhere as fast/sustainable iteration  
* CPU data \<-\> texture data is very easy  
* Multi-machine syncing  
* Particle systems  
* Pre-viz (with Unreal too)  
* Video:  
  * Alpha channel  
  * HAPq \- High-res  
* .fbx, .usd  
* Persistent variable values when closing/reopening software  
* Audio functionality & same audio context as VSTs

Disadvantages

* Multi-developer workflows. No code diffing  
* ???

### Questions

* When to write Python?  
  * When to keep logic in nodes?  
* How to organize? Can you relate to OOP concepts in coding? Extensions\!  
* How can you find the connections you’ve set up in the Parameter window & other “hidden” connections?  
* Events & event systems? Largely w/*select* & *dat exec* ops  
* How to collaborate & version control?  
* When do crashes happen? (besides using the wrong version of TD)  
* Building UIs?  
* Building Video Games?  
* Are there any drawing tools like p5js/Processing that let you draw shapes into a texture?

### Channels

* General resources  
  * [https://alltd.org/](https://alltd.org/)  
  * [https://matthewragan.com/teaching-resources/touchdesigner/](https://matthewragan.com/teaching-resources/touchdesigner/)   
  * [https://github.com/chungbwc/TouchDesigner](https://github.com/chungbwc/TouchDesigner)   
  * [https://github.com/DBraun/TouchDesigner\_Shared](https://github.com/DBraun/TouchDesigner_Shared)   
  * [https://github.com/vinz9/](https://github.com/vinz9/)   
* Tools  
  * [https://olib.amb-service.net/](https://olib.amb-service.net/) \- OLIB  
* Tutorials  
  * [https://docs.derivative.ca/index.php?title=Tutorials](https://docs.derivative.ca/index.php?title=Tutorials)   
  * [https://interactiveimmersivehq.github.io/touchdesigner-book/](https://interactiveimmersivehq.github.io/touchdesigner-book/)   
  * [https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/](https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/)   
  * [https://interactiveimmersive.io/blog/touchdesigner-lessons/touchdesigner-beginner-tricks/](https://interactiveimmersive.io/blog/touchdesigner-lessons/touchdesigner-beginner-tricks/)   
  * [TouchDesigner Beginner Crash Course](https://www.youtube.com/playlist?list=PLpuCjVEMQha9rjhDET3uuE0T3UeIcROJu)  
  * [Absolute Beginner TouchDesigner | From Zero to Hero with Examples and Assignments](https://www.youtube.com/watch?v=qbupHTeJCeU)  
  * [https://www.youtube.com/watch?v=guNquMaplW8\&list=PLm8zJ0HKEJIaVUQ5J7NTutC76WbVBSxLG\&index=27](https://www.youtube.com/watch?v=guNquMaplW8&list=PLm8zJ0HKEJIaVUQ5J7NTutC76WbVBSxLG&index=27) \- Gray Area class\!  
  * Torin:  
    * [Face, Hand, Pose Tracking & More in TouchDesigner with @MediaPipe GPU Plugin](https://www.youtube.com/watch?v=Cx4Ellaj6kk)   
    * [Audio-Reactive Visuals in TouchDesigner](https://www.youtube.com/watch?v=R7sAomk2vR4)   
  * Git / version control  
    * [TouchDesigner | Working Styles | Git – Matthew Ragan](https://matthewragan.com/2017/12/03/touchdesigner-working-styles-git/)  
    * [Teamwork & Version Control  a Git Workflow for TouchDesigner - Idzard Kwadijk](https://www.youtube.com/watch?v=aJ3Lur9zpKU)  
  * Organization tips  
    * [Simple PRO TouchDesigner Tips & Habits](https://www.youtube.com/watch?v=vE4FcgUS8jY)   
    * [How I Build TouchDesigner Apps in 2025 – Python, State Machines, Extensions](https://www.youtube.com/watch?v=nQT7EhYCVg0)  
  * Data in TD  
    * [TouchDesigner's Data Model - Tutorial](https://www.youtube.com/watch?v=Xvg8z_d6ZJU)  
    * [Widgets Part 9 - Binding to channels with the Bind CHOP](https://www.youtube.com/watch?v=bLi-xrCUt-c)  
  * Lots of techniques, connecting chops to params  
    * [Talking ball Starboy in Touchdesigner (터치디자이너 튜토리얼 자막)](https://www.youtube.com/watch?v=va6cxORsFMw)  
  * UI  
    * [TouchDesigner - UI Basics: Part 1 - How to make buttons](https://www.youtube.com/watch?v=UWtO-dVipO8&t=138s)  
    * [User interface with widgets in Touchdesigner](https://www.youtube.com/watch?v=m98BlIxM_cg)  
    * [Perform Mode / Projector Setup – TouchDesigner Tips, Tricks & FAQs 15](https://www.youtube.com/watch?v=UBmTkOCovus)  
  * Scripting  
    * [TouchDesigner 202 Berlin, Custom Parameters, Python and Extensions](https://www.youtube.com/watch?v=TaNzAfXEQew)  
    * [Deep dive into TD Dependency Class / Implementing observer pattern in TD.](https://www.youtube.com/watch?v=kEQAsx6Ar_8)  
    * [Python In TouchDesigner with Noah Norman](https://www.youtube.com/watch?v=3sQM7izOlIE)  
  * MIDI  
    * [TouchDesigner | Working with Midi 1/4](https://www.youtube.com/watch?v=XLeghJmFBh0&list=PLH-IBHIXahauD5cS7NA2YgkGV0FNcSQPM)  
    * [Touchdesigner - Midi controller quick start guide](https://www.youtube.com/watch?v=mF_v7L-I75M)  
  * Particles  
    * [Touchdesigner Tutorial - Versatile Particles System](https://www.youtube.com/watch?v=z6TaWv4fgsE)  
    * [Touchdesigner Tutorial - Advanced Pointclouds Manipulation](https://www.youtube.com/watch?v=dF0sj_R7DJY)  
    * [Interactive Installation Particle Systems with TouchDesigner](https://www.youtube.com/watch?v=Pifp7TTvWEw)   
    * [Point Clouds in TouchDesigner099 Part3 - Napoleon dissolved](https://www.youtube.com/watch?v=QB3P0-uCszo)  
    * [2D Particle System with TOPs - TouchDesigner Tutorial 01](https://www.youtube.com/watch?v=8AynfgNv6Ek)  
    * [Force Field Particle Effects In TouchDesigner](https://www.youtube.com/watch?v=bkRc6CrsndI)  
  * Audio  
    * [TouchDesigner Electronic Music Studio - Owen Kirby](https://www.youtube.com/watch?v=Xajdyh7kspk)  
    * [VST Plugins & Comments in TouchDesigner Experimental Build](https://www.youtube.com/watch?v=PH76ccSxde4)  
    * [Building a Step Sequencer for VSTs in TouchDesigner - Tutorial](https://www.youtube.com/watch?v=HnAy3y9_SHM)  
    * [https://learn.newmedia.dog/tutorials/touchdesigner/audio-analysis/](https://learn.newmedia.dog/tutorials/touchdesigner/audio-analysis/)   
    * Multichannel audio  
      * [https://forum.derivative.ca/t/chop-audio-renderer/177998/2](https://forum.derivative.ca/t/chop-audio-renderer/177998/2)   
      * [https://forum.derivative.ca/t/how-to-control-multiple-sound-clips-in-touch-desiger/183704/3](https://forum.derivative.ca/t/how-to-control-multiple-sound-clips-in-touch-desiger/183704/3)   
  * Pixel map output  
    * [THP 494 & 598 | Large Display Arrangement | TouchDesigner](https://www.youtube.com/watch?v=RVqNjJfE9Lg)  
  * Projection mapping  
    * [https://matthewragan.com/2019/08/06/touchdesigner-stoner-tricks/](https://matthewragan.com/2019/08/06/touchdesigner-stoner-tricks/)   
  * LED/ArtNet mapping  
    * [Intro to TouchDesigner for Pixel Mapping - Ben Voigt and Markus Heckmann](https://www.youtube.com/watch?v=ShYYcr30vJw)   
  * Using openCV python in TD  
    * [Easy Feature Tracking with Script TOP and OpenCV in TouchDesigner - Tutorial](https://www.youtube.com/watch?v=1Uw2PWTR_XM)  
    * [Tracking QR Codes in TouchDesigner with OpenCV and Script TOP - Tutorial](https://www.youtube.com/watch?v=Nd3KbtY7K1Q)  
    * [Exporting OpenCV processed Numpy array to TOP directly with Script TOP in TouchDesigner.](https://www.youtube.com/watch?v=uYl0vvmmSwE) \- simple OpenCV/numpy array code example  
    * [Detecting arbitrary images with OpenCV Template Matching in TouchDesigner](https://www.youtube.com/watch?v=UF7dujcBXGg)  
    * [https://derivative.ca/community-post/tutorial/anaconda-managing-python-environments-and-3rd-party-libraries-touchdesigner](https://derivative.ca/community-post/tutorial/anaconda-managing-python-environments-and-3rd-party-libraries-touchdesigner)   
    * [https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/Python/9-6-External-Modules.html](https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/Python/9-6-External-Modules.html)   
  * Watercolor  
    * [Watercolors – TouchDesigner Tutorial 23](https://www.youtube.com/watch?v=0nI8V7XZ7yk)   
    * [https://www.youtube.com/watch?v=9ynL-JckDkY](https://www.youtube.com/watch?v=9ynL-JckDkY)   
    * [Watercolor Hand Tracking Brush in TouchDesigner Tutorial](https://www.youtube.com/watch?v=IATX3biLoZg)   
  * Gaussian splatting  
    * [Light Up Gaussian Splatting\!\!](https://www.youtube.com/watch?v=axY-a_1TNng) (uses Unreal for rendering)  
    * [Finally, Gaussian Splatting in TouchDesigner\!](https://www.youtube.com/watch?v=es5Vy0VTJ8M)  
  * Kinect Azure  
    * [Kinect Azure Point Cloud in TouchDesigner - TouchDesigner Tutorial 068](https://www.youtube.com/watch?v=P_PjAr2Yzao)  
    * [3 methods for visualizing Kinect skeleton](https://www.youtube.com/watch?v=ETQLq1EvXJI)  
    * [Kinect Skeleton Basics - TouchDesigner Tutorial](https://www.youtube.com/watch?v=zW7iHrU_f3c)  
  * Pro display output  
    * [https://docs.derivative.ca/Direct\_Display\_Out\_TOP](https://docs.derivative.ca/Direct_Display_Out_TOP)   
    * [https://docs.derivative.ca/Blackmagic\_Design](https://docs.derivative.ca/Blackmagic_Design)   
  * Bookmarked  
    * Engine  
      * [https://interactiveimmersive.io/blog/touchdesigner-operators-tricks/the-overhauled-engine-comp-in-touchdesigner/](https://interactiveimmersive.io/blog/touchdesigner-operators-tricks/the-overhauled-engine-comp-in-touchdesigner/)   
      * [https://derivative.ca/UserGuide/Engine\_COMP](https://derivative.ca/UserGuide/Engine_COMP)   
    * [https://docs.python.org/3/tutorial/appetite.html](https://docs.python.org/3/tutorial/appetite.html)   
    * [https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/User\_Interface/2-3-Transport-Controls.html](https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/User_Interface/2-3-Transport-Controls.html)   
    * [https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/TOPs/3-3-Preloading-Movies.html](https://nvoid.gitbooks.io/introduction-to-touchdesigner/content/TOPs/3-3-Preloading-Movies.html)   
    * [https://learn.derivative.ca/courses/200-intermediate/lessons/203-chops-intermediate/topic/using-the-shuffle-chop/](https://learn.derivative.ca/courses/200-intermediate/lessons/203-chops-intermediate/topic/using-the-shuffle-chop/)   
    * [https://learn.derivative.ca/courses/200-intermediate/lessons/203-chops-intermediate/topic/sequencing-events-with-the-timer-chop/](https://learn.derivative.ca/courses/200-intermediate/lessons/203-chops-intermediate/topic/sequencing-events-with-the-timer-chop/) \- timer & text from dat  
    * [https://matthewragan.com/2015/03/29/ame-394-simple-vj-set-up-touchdesigner/](https://matthewragan.com/2015/03/29/ame-394-simple-vj-set-up-touchdesigner/)   
    * [https://alltd.org/uploader/davidbraun/](https://alltd.org/uploader/davidbraun/)   
      * [https://github.com/DBraun/TouchDesigner\_Shared/blob/master/Audio/low\_pass\_analysis.tox](https://github.com/DBraun/TouchDesigner_Shared/blob/master/Audio/low_pass_analysis.tox)   
      * [https://github.com/DBraun/TouchDesigner\_Shared/tree/master/TOPs](https://github.com/DBraun/TouchDesigner_Shared/tree/master/TOPs)	  
    * [Voronoi tricks in Touchdesigner](https://www.youtube.com/watch?v=54amDdU0eus)  
    * [Exploding Star - constraining a particle system to a sphere TOUCHDESIGNER TUTORIAL](https://www.youtube.com/watch?v=WS2Ww6zYgJw)  
    * [Dynamic Texture Grids – TouchDesigner Tutorial 62](https://www.youtube.com/watch?v=Eq5amV7obwg)  
    * [Depth Of Field (Tilt Shift) – TouchDesigner Tips, Tricks and FAQs 3](https://www.youtube.com/watch?v=EIBGGIdUJyc)  
    * [TouchDesigner | Working with Midi 3/4](https://www.youtube.com/watch?v=cPvjeikyP-A&list=PLH-IBHIXahauD5cS7NA2YgkGV0FNcSQPM&index=18) \- matt ragan  
    * [Circularization\_tut\_01](https://www.youtube.com/watch?v=7rHGF0wr0Ck) \- newnome beauton  
    * [16 – Instancing – TouchDesigner Beginner Course](https://www.youtube.com/watch?v=rYet0SwTYa0) \- elekktronaut  
    * [3/3 TouchDesigner Vol.035 Cooking, Optimization, & SceneChanger](https://www.youtube.com/watch?v=TBI-yq_iE60)  
    * [14 – Palette – TouchDesigner Beginner Course](https://www.youtube.com/watch?v=9RE2iKzRHAg&list=PLFrhecWXVn5862cxJgysq9PYSjLdfNiHz&index=31)  
    * [Advanced Techniques in Media Management, Sequencing and Playback - Peter Sistrom](https://www.youtube.com/watch?v=ufwO61zEAzo)  
    * [42 Python in Touchdesigner : "0 to Her0" :: Engine Based Mediaplayer](https://www.youtube.com/watch?v=knTkfUkiF_Q) \- unveil  
    * [21 Four things I was missing for years :-)  \_Touchdesigner](https://www.youtube.com/watch?v=yZDcfR-pS5Y)  
    * [Point Clouds Part 1 - Twisting Shrines :: Touchdesigner Work Stream](https://www.youtube.com/watch?v=VNmm3gijDwA)  
    * [Text Textures – TouchDesigner Tutorial 9](https://www.youtube.com/watch?v=kosFgK7DdCo) \- elekktronaut  
    * [Talking ball Starboy in Touchdesigner (터치디자이너 튜토리얼 자막)](https://www.youtube.com/watch?v=va6cxORsFMw)  
    * [Touchdesigner/ Particles Gpu - Optical flow](https://www.youtube.com/watch?v=PbyjenIvtIA)  
    * [Lillian F. Schwartz-Inspired Visual FX in TouchDesigner - TouchDesigner Tutorial 158](https://www.youtube.com/watch?v=vyJPhh490xE)  
    * [TouchDesigner | External Python Libraries | 7/8](https://www.youtube.com/watch?v=LFWcsx2Ic6g) \- matt ragan  
    * [Loading images in folders one by one in sequence with Folder DAT in TouchDesigner](https://www.youtube.com/watch?v=daJdb7N6u2E)  
    * [Generative Visuals with Particles & Kinect: TouchDesigner Tutorial 028](https://www.youtube.com/watch?v=mY7DavB0z2c)  
    * [Touchdesigner tutorial 05 - copy SOP stamping](https://www.youtube.com/watch?v=GaYmXCrFZ5U)  
    * [Pointcloud Tutorial - Part 2  \[Trailer\]](https://www.youtube.com/watch?v=WZh-TitB-Sk&list=PL4XNsp-R8i-LAHaSqlF8HfIpErYMBOxO5&index=19)  
    * [Demystifying TouchDesigner SOPs 9. Subdivide Geometry](https://www.youtube.com/watch?v=EyFQXs6QXYY)  
    * [Simple tornado with glsl (Touchdesigner tutorial)](https://www.youtube.com/watch?v=cm0oUBCtKms) \- noonesimg like newnome  
    * [Noise Displacement in TouchDesigner](https://www.youtube.com/watch?v=LWpUcaCHD3Q) \- polyhop  
    * [Teamwork & Version Control  a Git Workflow for TouchDesigner - Idzard Kwadijk](https://www.youtube.com/watch?v=aJ3Lur9zpKU)  
    * [Make Anything Audio Reactive – TouchDesigner Tips, Tricks and FAQs 12](https://www.youtube.com/watch?v=rGoCbVmGtPE)  
    * [Creator Session with Volvox Labs](https://www.youtube.com/watch?v=YZE1vyHB0UM)  
    * [AET 310 - Touchdesigner Project - Main Tutorial - Video 1 - Building the Background](https://www.youtube.com/watch?v=6ZVvhIuPyM0&list=PLmEFHC9k1VTbYPKu5O3ndgpsY7TKWInj9&index=13)  
    * [AME 394 | Multi Process Communication | TouchDesigner](https://www.youtube.com/watch?v=8BKuoFT0W3s&list=PLs0WlHa1rf23bIKTOO7AwY7FaSRExk2Go)  
    * [TD as Game Engine, Part 1: Structure](https://www.youtube.com/watch?v=Ucu2XhWibvg)  
    * [TouchDesigner \_04 Sliced Type](https://www.youtube.com/watch?v=DeCaJ5EwyIg)  
    * [TouchDesigner Electronic Music Studio - Owen Kirby](https://www.youtube.com/watch?v=Xajdyh7kspk)  
    * [Playing VSTs with MIDI in TouchDesigner - TouchDesigner Tutorial 074](https://www.youtube.com/watch?v=8o6_v-a0Jxg)  
    * [Deconstructing Sculptures - Pointclouds and 3d-models TOUCHDESIGNER TUTORIAL](https://www.youtube.com/watch?v=ruHVM5KZjB8)  
    * [Particle System Following the Geometry Surface | Touchdesinger Tutorial](https://www.youtube.com/watch?v=nqTpxNIuNdA&sttick=0)  
    * [substrate algorithm in TouchDesigner](https://www.youtube.com/watch?v=JBrFLv_kaIE)  
    * [Filtered Pointclouds - Beginner Touchdesigner Tutorial](https://www.youtube.com/watch?v=2SXYHuB42Ek)  
    * [TouchDesigner \_06 Fluid Simulation](https://www.youtube.com/watch?v=2k6H5Qa_fCE)  
    * [TouchDesigner \_03 Curl Noise](https://www.youtube.com/watch?v=DkSwEY-m9GA)  
    * [Animating Noise - TouchDesigner 10](https://www.youtube.com/watch?v=dwh5CS_0EDs)  
    * [Versatile Sprinkle SOP (TouchDesigner tutorial)](https://www.youtube.com/watch?v=Xlyo-njdWcg&sttick=0)  
    * [Motion Tracking with TouchDesigner & MediaPipe - TouchDesigner Tutorial 196](https://www.youtube.com/watch?v=6uibOShiOnU)  
    * [TOUCHDESIGNER Tutorial - Particles SOP](https://www.youtube.com/watch?v=zKzwvBzHKbU)  
    * [Deconstructing Sculptures - Pointclouds and 3d-models TOUCHDESIGNER TUTORIAL](https://www.youtube.com/watch?v=ruHVM5KZjB8&t=4s)  
    * [datamosh in Touchdesigner](https://www.youtube.com/watch?v=_MJ71LyBAjk)  
    * [\[TouchDesigner - Component\] TauCeti Preset Manager 3.0](https://www.youtube.com/watch?v=SSNvsvrnifI)  
    * [Instancing with the Event CHOP in TouchDesigner - TouchDesigner Tutorial 204](https://www.youtube.com/watch?v=6m5245cCSdo)  
    * [How To Set Up Your Laser To Beyond & TouchDesigner](https://www.youtube.com/watch?v=LdWmvYSK8Zs)  
    * [https://www.youtube.com/@datlabnyc/streams](https://www.youtube.com/@datlabnyc/streams)   
    * [TouchDesigner Tutorial | Kinetic Typography](https://www.youtube.com/watch?v=BMseVh0eSnY)  
    * [TouchDesigner | How to Create Multiple and Diverse Visuals with Just 10 Nodes | Beginner Tutorial](https://www.youtube.com/watch?v=03_bzTa6_HM)  
    * [.PNG into particles | Reorder TOP explained | TouchDesigner Tutorial](https://www.youtube.com/watch?v=CcvhTgD7IOI)  
    * [Interconnected Particles Only Using TOPs | Touchdesigner Tutorial](https://www.youtube.com/watch?v=vtVoVLChgsY)  
    * [5 Ways To Make Particles in TouchDesigner](https://www.youtube.com/watch?v=kNeSa7XivUs)  
    * Reflections  
      * [Touchdesigner Tutorial: Reflective Surfaces](https://www.youtube.com/watch?v=8kJWbsU2vbE)  
    * POPs  
      * [TouchDesigner POPs Instance Field - TouchDesigner Tutorial 202](https://www.youtube.com/watch?v=q8OOyyvhmbs)  
      * [Physics in TouchDesigner POPs (Experimental)](https://www.youtube.com/watch?v=hqplK_Gsw8E)	  
      * [POPs Alive: Bring Particle Life to TouchDesigner (EXPERIMENTAL)](https://www.youtube.com/watch?v=yfDHqNEuiZQ)  
      * [Ray POP Tutorial in Touchdesigner](https://www.youtube.com/watch?v=_V43LruvtPw)  
      * [2D Raycasting with TouchDesigner POPs](https://www.youtube.com/watch?v=KydJUFlHFbA)  
      * [48 :: THE GLSL COPY POP:: pt3 \#touchdesigner](https://www.youtube.com/watch?v=1T8T5TXjxIQ)  
      * [Text particles with POPs | Part 1: Touchdesigner, POPs, Text, 3D Textures, instancing](https://www.youtube.com/watch?v=s9edKgoumJw) \- Memo Akten  
      * [GLSL for POPs in TouchDesigner: Lesson 1 (Attribute Blur and Neighbor POP)](https://www.youtube.com/watch?v=9BPTB7_IU7Q)  
      * [48 :: THE GLSL COPY POP:: pt3](https://www.youtube.com/watch?v=1T8T5TXjxIQ)  
      * [Strange Attractor GLSL POP - TouchDesigner Tutorial](https://www.youtube.com/watch?v=Ty3u7qfPj2E)  
      * [Flocking with POPs in TouchDesigner](https://www.youtube.com/watch?v=7_y2he5-_Q4)✅  
      * [TouchDesigner POPs Tutorial: Transform Any Video To Particles - Webcam, Live, Streaming](https://www.youtube.com/watch?v=_FSuwMFDLs8)  
      * [TouchDesigner Tutorial | Distance Constrain Chain](https://www.youtube.com/watch?v=PQmBJf9uvf0)  
      * [TouchDesigner Workshop Intro to POPs | Gravity Particle System](https://www.youtube.com/watch?v=HFZI4lS0mls)  
      * [First POP Experiments Part 1 – TouchDesigner Tutorial 74](https://www.youtube.com/watch?v=B-WJrAIw7Y0)  
      * [TouchDesigner Meetup -- POPs Q&A -- December 2025](https://www.youtube.com/watch?v=b6bzhFImXtM)  
    * [How I Build TouchDesigner Apps in 2025 – Python, State Machines, Extensions](https://www.youtube.com/watch?v=nQT7EhYCVg0)✅  
    * [Smooth Point Cloud Sprinkles with UV Unwrapping in TouchDesigner](https://www.youtube.com/watch?v=U0JRJHGIRug)  
    * [3 ASCII Patterns - WEBCAM, NOISE, Input Movie: Touchdesigner Tutorial](https://www.youtube.com/watch?v=_hPY1hFSa64) ✅  
    * Blob tracking  
      *  [Unlimited Blob Tracking in TouchDesigner](https://www.youtube.com/watch?v=fEkWTWDr6Fc)   
        * Lines between blobs (11:00-ish)  
        * Text overlay (25:00-ish)  
    * [TouchDesigner Meetup - Shaders - June 2024 / Tekt, Josef, Jason](https://www.youtube.com/watch?v=JJabRuWLNzQ) ✅  
    * [DATLAB TouchDesigner Meetup X Livestream](https://www.youtube.com/watch?v=VbbWoJYkhzQ) \- LOPs, Matterform ✅  
    * [Armin Hoffman Shape Generator in TouchDesigner](https://www.youtube.com/watch?v=bUK_FZ2Ujbc)  
    * [Touchdesigner Tutorial - 3D Rendering with buffers](https://www.youtube.com/watch?v=aVYqxKpI77g)  
    * [Depth Body Tracking x Interactive Particle with WebCam](https://www.youtube.com/watch?v=EO5bQgerW5U) \- BodyTrack CHOP  
    * [Liquid glass | TouchDesigner Tutorial](https://www.youtube.com/watch?v=lc9gZwFgI1w)  
    * [CHOP Anatomy: Building-blocks of a CHOP \[Part 1\]](https://www.youtube.com/watch?v=r0dVSn-ZFPw)  
    * [Format Bending #1 - Image2Audio2Image/wavetable weirdness](https://www.youtube.com/watch?v=NtpqL53gyqc)  
    * Unreal integrations  
      * [TouchDesigner and Unreal Engine Integrations](https://www.youtube.com/watch?v=Nd9Ld-R_AxA) (gpu particles)  
* Channels  
  * [https://www.youtube.com/@TheInteractiveImmersiveHQ/videos](https://www.youtube.com/@TheInteractiveImmersiveHQ/videos)   
  * [https://www.youtube.com/@elekktronaut/videos](https://www.youtube.com/@elekktronaut/videos)  
  * [https://www.youtube.com/@paketa12/videos](https://www.youtube.com/@paketa12/videos)  
    * [https://derivative.ca/user/76325/profile?sort_by=views](https://derivative.ca/user/76325/profile?sort_by=views)   
  * [https://www.youtube.com/@raganmd/videos](https://www.youtube.com/@raganmd/videos)   
  * [https://www.youtube.com/user/Wuestenarchitekten/videos](https://www.youtube.com/user/Wuestenarchitekten/videos)   
  * [https://www.youtube.com/@blankensmithing/videos](https://www.youtube.com/@blankensmithing/videos)   
  * [https://www.youtube.com/@dotsimulate/videos](https://www.youtube.com/@dotsimulate/videos)   
  * [https://www.youtube.com/@FunctionStore/videos](https://www.youtube.com/@FunctionStore/videos)   
  * [https://www.youtube.com/@cutmod/videos](https://www.youtube.com/@cutmod/videos)   
  * [https://www.youtube.com/@threedashes___/videos](https://www.youtube.com/@threedashes___/videos)  
  * [https://www.youtube.com/@akenbak/videos](https://www.youtube.com/@akenbak/videos)  
  * [https://www.youtube.com/@noonesimg](https://www.youtube.com/@noonesimg)   
  * [https://www.youtube.com/@TouchDesignerOfficial/videos](https://www.youtube.com/@TouchDesignerOfficial/videos)  
  * [https://www.youtube.com/@acrylicode/videos](https://www.youtube.com/@acrylicode/videos)  
  * [https://www.youtube.com/@FunctionStore/videos](https://www.youtube.com/@FunctionStore/videos)  
  * [https://www.youtube.com/@newnome_beauton](https://www.youtube.com/@newnome_beauton)  
  * [https://www.youtube.com/@NotoTheTalkingBall](https://www.youtube.com/@NotoTheTalkingBall)   
  * [https://www.youtube.com/@polyhop](https://www.youtube.com/@polyhop)   
    * [https://www.simonaa.media/tutorials-articles](https://www.simonaa.media/tutorials-articles)   
  * [https://www.youtube.com/@StanislavGlazov/videos](https://www.youtube.com/@StanislavGlazov/videos)   
  * [https://www.youtube.com/@pppanik007/videos](https://www.youtube.com/@pppanik007/videos)   
  * [https://www.youtube.com/@supermarketsallad/videos](https://www.youtube.com/@supermarketsallad/videos)   
  * [https://www.youtube.com/@unveil7762/videos](https://www.youtube.com/@unveil7762/videos)   
  * [https://www.youtube.com/@TDSW-online/videos](https://www.youtube.com/@TDSW-online/videos)   
  * [https://www.youtube.com/@thirdwavearcade](https://www.youtube.com/@thirdwavearcade)   
  * [https://www.youtube.com/@_mini_uv/videos](https://www.youtube.com/@_mini_uv/videos)   
  * [https://www.youtube.com/@pao_olea/videos](https://www.youtube.com/@pao_olea/videos)   
  * [https://www.youtube.com/@pjcreated/videos](https://www.youtube.com/@pjcreated/videos)   
  * [https://www.youtube.com/@water__shed/videos](https://www.youtube.com/@water__shed/videos)   
  * [https://www.youtube.com/@BlakeMarquesCarrington/videos](https://www.youtube.com/@BlakeMarquesCarrington/videos)   
  * [https://www.youtube.com/channel/UCUDA_BAggznRrms3YFva2ag/videos](https://www.youtube.com/channel/UCUDA_BAggznRrms3YFva2ag/videos)   
  * [https://www.youtube.com/@TheVisualCast/videos](https://www.youtube.com/@TheVisualCast/videos)	  
  * [https://www.youtube.com/@threedashes___/videos](https://www.youtube.com/@threedashes___/videos)   
  * [https://www.youtube.com/@De_Re/videos](https://www.youtube.com/@De_Re/videos)   
  * [https://www.youtube.com/@ab_out7036/videos](https://www.youtube.com/@ab_out7036/videos)   
  * [https://www.youtube.com/@as_ws/videos](https://www.youtube.com/@as_ws/videos)   
  * [https://www.youtube.com/@OkamirufuV/videos](https://www.youtube.com/@OkamirufuV/videos)   
  * [https://www.youtube.com/@Diogo_888/videos](https://www.youtube.com/@Diogo_888/videos) \- typography\!  
  * [https://www.youtube.com/@FactorySettings/videos](https://www.youtube.com/@FactorySettings/videos)   
  * [https://www.youtube.com/@g3n0m4_xyz/videos](https://www.youtube.com/@g3n0m4_xyz/videos)	  
  * [https://www.youtube.com/@unveil7762/videos](https://www.youtube.com/@unveil7762/videos)   
  * [https://www.youtube.com/@xtalcalx](https://www.youtube.com/@xtalcalx) 
  * [https://www.youtube.com/@sarv.live7](https://www.youtube.com/@sarv.live7) 
