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
  * Shift + C for a comment\!  
  * ALT + S for project search  
  * ALT + S for floating textport window  
* Python snips  
  * Set a node’s parameter:  
    **op(‘noise1’).par.period = 1**  
  * Get a node’s parameter (numeric)  
    **op.par.Smoothrange.eval()**  
    **me.parent().par.Smoothrange.eval()**  
  * Get the first input of an op (useful when reading data)  
    **op.inputs[0]**  
  * Make a connection between nodes  
    **op.outputConnectors[0].connect(op2)**  
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
  * ALT + mouse hover to get a parameter tip  
* Panes  
  * ALT + Z - close pane w/mouse inside  
  * ALT + [ or ] - split cur pane  
* Locations (secret)  
  * /sys  
  * /ui  
  * /local/time  
* Operator menu  
  * Darker options are "generators"  
* Network tricks  
  * Select multiple items to change parameters on all  
  * ALT + N to add a null after the selected TOP  
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
  * Constant TOP - use this with rgba(0,0,0,0) to create a specific-sized FBO for compositing  
  * Order in composite TOPs like Over depend on the order of inputs  
  * Use multiple Over TOPs to add multiple graphics to a composite - this lets you treat each new additional texture with its own parameters, which will probably be different from each other  
  * Blend modes:   
    * In Palette, “blendModes” example shows lots of blending previews  
    * In Composite TOP parameters, “Preview Grid” toggle will show all possible blend modes. If you see one split, that shows the result of different-ordered inputs  
* Interpolating numbers  
  * Lag & Filter CHOPs help with this. Lag has a time for up/down, and Filter uses the same for both  
* Data  
  * [TouchDesigner's Data Model - Tutorial](https://www.youtube.com/watch?v=Xvg8z_d6ZJU)  
* Expressions  
  * me.digits - grabs the end number of your node  
* To kill a bunch of nodes, select all w/ctrl + a, right-click on empty space and “Collapse selected”, then click the ‘x’ on the Component node to turn off cooking  
* Facet SOP: Unique Points & 2nd Computer Normals to get low-poly lighting  
* self in Python  
  * [What is "self" in Python?](https://www.youtube.com/watch?v=oaiQ5hYKHTE)  
  * [How bound methods are the key to understanding SELF in Python.](https://www.youtube.com/watch?v=x4j6bzbbx2o)   
* Python paths  
  * C:\Program Files\Derivative\TouchDesigner\bin\Lib\site-packages  
    * System var path:   
      C:\msys64\ucrt64\bin  
    * User var path  
      C:\Users\cacheflowe\AppData\Roaming\Python\Python311\Scripts  
  * [Anaconda - Managing Python Environments and 3rd-Party Libraries in TouchDesigner | Derivative](https://derivative.ca/community-post/tutorial/anaconda-managing-python-environments-and-3rd-party-libraries-touchdesigner)   
  * [How to use external python libraries in Touchdesigner](https://www.youtube.com/watch?v=_U5gcTEsupE)  
  * [External Python Libraries | Derivative](https://derivative.ca/community-post/tutorial/external-python-libraries/61022) - Matt Ragan external python tutorials  
  * [https://derivative.ca/UserGuide/Category:Python](https://derivative.ca/UserGuide/Category:Python)   
  * [GeoPix V2 - Getting Started #1 - Installation & Setup](https://www.youtube.com/watch?v=HEdTy6hLl4c)   
  * [TouchDesigner Tutorial : Embedding External Python libraries inside of TOE file](https://www.youtube.com/watch?v=c-pZa9QrTvk)
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
* CPU data <-\> texture data is very easy  
* Multi-machine syncing  
* Particle systems  
* Pre-viz (with Unreal too)  
* Video:  
  * Alpha channel  
  * HAPq - High-res  
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

