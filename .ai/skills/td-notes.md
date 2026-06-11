---
name: td-notes
description: TouchDesigner cheatsheet — keyboard shortcuts, network navigation, Python quick-reference, compositing tips, performance resources, and TD philosophy. Use as a quick reference for TD UI and workflow.
---

# TouchDesigner Notes

## Documentation

- https://derivative.ca/UserGuide
- https://derivative.ca/UserGuide/More_Things_to_Know_about_TouchDesigner
- https://derivative.ca/UserGuide/Project_Class
- https://derivative.ca/UserGuide/AbsTime_Class
- https://derivative.ca/UserGuide/Performance_Monitor

## Key Commands

- https://derivative.ca/UserGuide/Application_Shortcuts
- Network nav: I (in), U (up), H (home)
- TAB — operator search
- P — toggle Parameter window
- Shift + C — add a comment
- ALT + S — project search / floating textport window

## Python Quick Reference

```python
# Set a node's parameter
op('noise1').par.period = 1

# Get a node's parameter (numeric)
op.par.Smoothrange.eval()
me.parent().par.Smoothrange.eval()

# Get the first input of an op
op.inputs[0]

# Connect nodes
op.outputConnectors[0].connect(op2)

# Loop through replicants with index
for i, c in enumerate(newOps):
    pass

# Use parent Container size to scale a UI element
me.parent.width()

# run() with delay from extension
run("parent().SampleTriggerOff()", fromOP=me, delayFrames=1)
run(f"op('{self.ownerComp.path}').PulseTriggerLaunch()", delayFrames=delayFrames)

# Call a function in another DAT
op('text_other_script').module.function_name()
```

## Parameter Window Tips

- Hover, then click & hold for different drag scales, then drag left/right while still holding
- Click "I" for the node's info window
- Click "?" for help info. 2nd "?" is python help
- ALT + mouse hover for a parameter tip

## Pane Controls

- ALT + Z — close pane (mouse inside)
- ALT + [ or ] — split current pane

## Hidden Locations

- `/sys`
- `/ui`
- `/local/time`

## Operator Menu

- Darker options are "generators"

## Network Tricks

- Select multiple items to change parameters on all
- ALT + N — add a null after the selected TOP
- Right-click existing output connection to insert in between
- Middle click to create a new branch

## Create a Base COMP Component

1. Create multiple nodes, right-click network background, do Collapse Selected, add null at the end for output
2. Create Select node outside the base component, split pane, drag the null TOP over to Select's Parameter window as the source TOP
3. Reuse: give the node a name, open TD palette, add a folder in My Components, drag your BaseComp into it
4. The Select TOP allows dynamically switching texture sources. Alternatively, create an Out TOP to give the BaseComp an output connector

## Create a Component/Extension with Python

- https://derivative.ca/UserGuide/Extensions
- Create a Base Component, right-click and choose Customize Component to open the Component Editor
- In the Extensions dropdown, enter the name of the component and click Add
- Add custom parameters accessible inside the Base COMP
- https://interactiveimmersive.io/blog/deployment/large-scale-touchdesigner-projects/

## Compositing

- Constant TOP — use with `rgba(0,0,0,0)` to create a specific-sized FBO for compositing
- Order in composite TOPs like Over depends on the order of inputs
- Use multiple Over TOPs to add multiple graphics to a composite — each new texture can have its own parameters
- Blend modes:
  - In Palette, "blendModes" example shows all blending previews
  - In Composite TOP parameters, "Preview Grid" toggle shows all possible blend modes. Split preview = result of different-ordered inputs

## Interpolating Numbers

Lag & Filter CHOPs. Lag has separate up/down times, Filter uses the same for both.

## Expressions

- `me.digits` — grabs the trailing number of your node name

## Kill a Bunch of Nodes

Select all (Ctrl+A), right-click on empty space and Collapse Selected, then click the 'x' on the Component node to turn off cooking.

## Geometry

- Facet SOP: Unique Points + Compute Normals → low-poly lighting

## Feedback

Needs Comp order change.

## Data

- [TouchDesigner's Data Model - Tutorial](https://www.youtube.com/watch?v=Xvg8z_d6ZJU)

## Python Paths

```
C:\Program Files\Derivative\TouchDesigner\bin\Lib\site-packages
C:\msys64\ucrt64\bin  (system var path)
C:\Users\<user>\AppData\Roaming\Python\Python311\Scripts  (user var path)
```

- https://derivative.ca/community-post/tutorial/anaconda-managing-python-environments-and-3rd-party-libraries-touchdesigner
- https://derivative.ca/UserGuide/Category:Python

## Optimization & Performance

- https://derivative.ca/UserGuide/Optimize
- [The Ultimate Movie Loading Guide For TouchDesigner Projects](https://www.youtube.com/watch?v=EGrBcoH5fjc)
- [Easy Optimization Tricks in TouchDesigner](https://www.youtube.com/watch?v=3XniGOP4V0k)
- [Permanent Installation Autostart Scripts](https://www.youtube.com/watch?v=-djb6U-ntyY)
- [Best Practices for TouchDesigner Collaboration](https://www.youtube.com/watch?v=6KPwrmrBoAE)
- [Cooking, Optimization, & SceneChanger](https://www.youtube.com/watch?v=JpTv_aZam-I)
- [Engine COMP in TouchDesigner](https://www.youtube.com/watch?v=Fau61Cz80iY)
- [Advanced Media Management, Sequencing and Playback](https://www.youtube.com/watch?v=ufwO61zEAzo)

## Deeper Tools

- https://github.com/mhammond/pywin32
- https://github.com/IntentDev/touchpy
- SVG tools

## Shell Scripts

- [Startup Configuration with Environment Variables — Matthew Ragan](https://matthewragan.com/2019/08/05/touchdesigner-start-up-configuration-with-environment-variables/)

## Threading Reference

- https://derivative.ca/UserGuide/Run_Command_Examples

---

## TD Advantages

- Visualization of graphics operation chains (shaders, compositing, etc)
- Instant UI for everything
- Real-time editing
- CPU data ↔ texture data is easy
- Multi-machine syncing
- Particle systems
- Pre-viz (with Unreal too)
- Video: alpha channel, HAPq high-res
- .fbx, .usd
- Persistent variable values when closing/reopening
- Audio functionality & same audio context as VSTs

## TD Disadvantages

- Multi-developer workflows — no code diffing

## See Also

- [.ai/skills/td-snippets.md](.ai/skills/td-snippets.md) — quick Python code snippets
- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — task-oriented Python patterns
