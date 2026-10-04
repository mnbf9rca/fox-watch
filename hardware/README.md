# Fox Watch hardware

## Camera tray and standoff

One-piece PLA holder: a 28 × 26.862 mm internal tray on a flared central column and a 34 × 34 × 4 mm slotted foot. The PCB sits on four 5 mm-high, Ø4.5 mm stands; walls rise 6 mm above its front. A 16.4 mm opening on +Y leaves the centred ribbon exit open.

Camera dimensions follow [Raspberry Pi's official standard-lens drawing](https://datasheets.raspberrypi.com/camera/camera-module-3-standard-mechanical-drawing.pdf): 25 × 23.862 mm PCB, 1.12 mm thickness, Ø2.2 mm mounting holes on a 21 × 12.5 mm pattern, and 11.3 mm overall depth. The model infers `lens_from_pcb_rear = 8.55` mm by subtracting the 2.75 mm rear connector projection; confirm that distance at the lens's furthest focus position before final assembly.

Parameters are at the top of `camera-standoff.scad`: original enclosure-height reference 94 mm, nominal lens gap 8.5 mm, downward tilt 0° (range 0–20°), tray extra size 3 mm, wall/floor thickness 2 mm, stand height 5 mm and wall height above PCB front 6 mm. `column_extension = 9` applies the measured fit correction, adding 9 mm to the vertical column and raising the entire flare and tray. At zero tilt the straight column above the foot is 63.75 mm long, tray underside 78.95 mm, PCB rear 85.95 mm and rim 93.07 mm above the mounting plate. The height calculation now uses a 103 mm effective reference; check the actual cover-to-lens clearance on the corrected assembly.

The assumed grid pitch is 5 mm with 3 mm plate holes; verify the pitch before printing. Four grid intervals give a 20 × 20 mm mounting pattern, with four 8 × 2.2 mm slots for M2 bolts and ±2.9 mm adjustment along Y. Change `grid_pitch`, interval counts or bolt diameter to suit; `clearance = 0.2` mm is added to bolt diameters. Assertions reject settings that put slots outside the foot or into the column.

Print foot down on the A1 mini in PLA, using its usual PLA profile, 0.4 mm nozzle, 0.2 mm layers, four walls, five top/bottom layers and 25% infill. Disable supports; the flare supports the tray. Use a brim if needed.

Mount the camera with four nominal 2 mm self-tapping screws and small nonconductive washers, tightening gently by hand; only the stands should touch the PCB. The blind pilots default to Ø1.6 mm and 6 mm depth (`camera_pilot_diameter`, `camera_pilot_depth`); tune the diameter for your actual screws. Choose length so penetration after the 1.12 mm PCB and washer remains below 6 mm; a 6 mm-long screw provides about 4.9 mm penetration before allowing for the washer. Fix the foot with M2 buttonhead hex bolts and nuts behind the mounting plate, choosing length for the 4 mm foot plus plate, washers and nut. Connect the ribbon with power off and leave a loose bend through +Y.

Attach the user-cut 10 mm black foam ring to the fixed tray rim, spanning the ribbon notch and surrounding the camera. Choose foam thickness from the actual rim-to-cover gap after the column-height correction. Keep its opening clear of the moving lens and the optical field; tilt requires a wedge-shaped foam fit. Check physical clearance through focus travel with the cover closed; physical fit, foam compression and printing have not been tested.

Export after parameter changes from the repository root: `/opt/homebrew/bin/openscad --hardwarnings -o hardware/camera-standoff.stl hardware/camera-standoff.scad`.

## Camera base extension

`camera-base-extension.scad` and `camera-base-extension.stl` provide a separate 34 × 34 × 9 mm spacer for an already-printed original-height stand. It matches the rounded foot and four 8 × 2.2 mm mounting slots on a 20 × 20 mm pattern. Parameters at the top control height, footprint and mounting dimensions; keep the mounting dimensions matched to the stand. Use it beneath the original stand (`column_extension = 0`), choosing M2 bolts 9 mm longer for the same plate, washers and nuts. The stand plus spacer reaches 93.07 mm overall at zero tilt; the current extended stand already includes this height correction.

Print flat in PLA on the A1 mini with a 0.4 mm nozzle, 0.2 mm layers, four walls, five top/bottom layers and 10% sparse infill, with supports disabled. Export after changes: `/opt/homebrew/bin/openscad --hardwarnings -o hardware/camera-base-extension.stl hardware/camera-base-extension.scad`.

## Pi 4B light shield

`pi-barn.scad` and `pi-barn.stl` form an open-bottom cover with 60 × 100 × 40 mm clear interior, a solid 2 mm roof and 2 mm side walls. The body is 64 × 104 × 42 mm; mounting ears make the total footprint 76 × 104 mm. Side diamond vents leave an opaque 8 mm upper band. Use dark opaque PLA to reduce light reaching the enclosure lid.

Orient the Pi with Ethernet toward +Y, microSD toward −Y, and USB-C toward +X, centred within the cover. Opening positions use [the official Pi 4 mechanical drawing](https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-mechanical-drawing.pdf), with cutouts: USB-C 12 × 24 mm, Ethernet 22 × 26 mm, microSD 24 × 12 mm and a 16.4 × 2.4 mm ribbon slot at 16 mm above the plate. The ribbon exits the short microSD edge (−Y), offset 16.5 mm toward +X to align with the CSI connector's plane; `ribbon_end = 1` moves it to the Ethernet edge, and `ribbon_center_x` tunes alignment. The three port notches open to the plate; the USB-C opening clears the mounting ear. Adjust opening positions and heights for the actual Pi standoffs and plugs; the measured 25 mm PoE assembly leaves 15 mm minus mounting-standoff height below the roof.

The Pi remains mounted on its own four standoffs. Four M2 buttonhead hex bolts secure the cover through 6 × 2.2 mm slots on a nominal 70 × 90 mm pattern, with nuts behind the plate. The 14 mm-long ears meet the body ends on the assumed 5 mm grid; verify the grid and available footprint. Choose bolt length for the 3 mm ears, plate thickness and nut; buttonheads have flat seats between the ear ribs.

The barn STL is already roof-down for printing on the A1 mini. Use PLA, 0.4 mm nozzle, 0.2 mm layers and four walls with supports disabled. The diamond slopes and ear ribs support the walls and tabs; inspect the short ear bridges and 16.4 mm ribbon-slot bridge in the slicer. Feed the disconnected ribbon through its slot before securing the cover, check SD access and fan/plug clearance, and confirm airflow with the assembly running. Physical assembly and printing have not been tested.

Export after parameter changes: `/opt/homebrew/bin/openscad --hardwarnings -o hardware/pi-barn.stl hardware/pi-barn.scad`.
