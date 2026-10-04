# Camera calibration

Measured on 2026-10-04 with the Camera Module 3 NoIR (standard lens) mounted low on the near-side bed, looking across the lawn towards the house. The numbers are valid only while the camera does not move. If it is nudged, turned or remounted, repeat the measurement (section "Repeating it").

## Camera settings at the time

Recorder settings from the Pi's `/etc/foxcam.env`: sensor mode 2304x1296 full field, output 1920x1080 at 10 fps, `--rotation 180`, `--lens-position 1.3`, `AWB_GAINS=1.0,1.0`. All image coordinates below are in full-sensor stills at 2304x1296 (taken with `rpicam-still --mode 2304:1296:10:P --width 2304 --height 1296` and the same rotation and focus). Multiply by 0.8333 for coordinates in the 1920x1080 recording.

## Camera model

Horizontal field of view 66 degrees, so the focal length is f = 1152 / tan(33°) = 1774 pixels at 2304 wide, or 1478 pixels at 1920 wide. The principal point is taken as the image centre, (1152, 648) at 2304x1296. Lens distortion was not measured and is small for this lens; residuals below are within about 6 percent.

- **Bearing** of an image column x: atan((x − 1152) / 1774), positive to the right.
- **Size rule**: an object of height h metres at depth Z metres along the camera axis spans 1774 · h / Z pixels. Z is depth along the axis, not straight-line distance: Z = range · cos(bearing).

## Measurements

Marker: a soda-maker gas cylinder, 30 cm tall including the valve and 6 cm wide, standing upright. Ranges were measured with a tape from the camera along the ground. Image positions are the base of the cylinder where it meets the ground.

| Point | Range | Image x, y (base) | Bearing | Height measured | Height predicted |
|---|---|---|---|---|---|
| Tape at 2 m | 2.00 m | 881, 735 | 8.7° left | 265 px | 269 px |
| Tape at 4 m | 4.00 m | 858, 582 | 9.4° left | 138 px | 135 px |
| Cross point, tape crossing | 4.21 m (from 4.9 m and 2.5 m) | 847, 593 | 9.8° left | | |
| Middle right, 2.5 m right of the cross point | 4.90 m | 1874, 514 | 22.1° right | 130 px | 117 px |
| Left | 6.20 m | 156, 582 | 29.3° left | 104 px | 98 px |
| Rear right | 8.50 m | 1597, 439 | 14.1° right | 68 px | 65 px |
| Rear left | 9.05 m | 723, 484 | 13.6° left | 61 px | 61 px |
| Back of grass on the lawn centre line | 8.80 m | 1281, 444 | 4.2° right | | |

The patio wall is 9.5 m from the camera along the centre line. The middle right cylinder's top merges with the shrub behind it, so its position is more reliable than its height.

Check: the distance between the cross point and the middle right cylinder computed from the image is 2.59 m against 2.5 m by tape.

## Ground positions

Camera at (0, 0); forward is along the camera axis; across is positive to the right. In metres: across = range · sin(bearing), forward = range · cos(bearing).

| Point | Across | Forward |
|---|---|---|
| Tape at 2 m | −0.30 | 1.98 |
| Tape at 4 m | −0.65 | 3.95 |
| Cross point | −0.71 | 4.15 |
| Middle right | +1.84 | 4.54 |
| Left | −3.03 | 5.41 |
| Rear right | +2.07 | 8.24 |
| Rear left | −2.13 | 8.80 |
| Back of grass, centre line | +0.64 | 8.78 |

These eight image-to-ground pairs are enough to fit a ground mapping. The lawn rises away from the camera and is slightly higher on the right, so fit a mapping that tolerates a non-planar ground, for example a homography fitted by least squares, and report its residuals; a single plane will be out by a few tenths of a metre at the far edge.

## Coverage

The camera axis points about 4 degrees left of the lawn's centre line, so the view extends further on the left. Measured perpendicular to the centre line at the back of the grass, 8.8 m out, the view reaches about 6.7 m left and 4.8 m right of it. Measured perpendicular to the cross-measurement tape at the cross point, 4.2 m out, it reaches about 1.8 m left and 3.9 m right; the cylinder 2.5 m left of that point was outside the frame. The near corners of the lawn, close to the camera on either side, fall outside the 66 degree view.

## Pixels on target

From the size rule, at depth Z the full-sensor still has 1774 / Z pixels per metre and the 1920x1080 recording has 1478 / Z.

| Depth | Hedgehog, 25 cm long | Fox, 70 cm long | Small bird, 12 cm |
|---|---|---|---|
| 2 m | 185 px | 517 px | 89 px |
| 5 m | 74 px | 207 px | 35 px |
| 9 m | 41 px | 115 px | 20 px |

Figures are for the 1920x1080 recording.

## Repeating it

Stop the recorder, take a still with the recorder's settings, then restart it:

```
sudo systemctl stop foxcam-record.service
rpicam-still --nopreview --mode 2304:1296:10:P --width 2304 --height 1296 --rotation 180 --autofocus-mode manual --lens-position 1.3 --awbgains 1.0,1.0 --denoise cdn_hq -t 3000 -o /tmp/cal.jpg
sudo systemctl start foxcam-record.service
```

Place a marker of known height at several measured points spread across the lawn: at least two on a tape from the camera, two either side of it at mid distance, and two at the far edge. Record each range from the camera and, for points off the tape, the offset from it. Read each marker's base position and height from the still and recompute the tables above.

## Photos

Camera stills at 2304x1296 with the recorder's settings, and phone photos of the setup. All metadata except the colour profile has been stripped.

- [Rear markers at 8.5 m and 9.05 m](calibration/01-camera-rear-markers-8.5m-9.05m.jpg)
- [Markers on the tape at 2 m and 4 m](calibration/02-camera-tape-markers-2m-4m.jpg)
- [Cross tape at 4.2 m, middle right marker at 4.9 m](calibration/03-camera-cross-tape-4.2m.jpg)
- [Left marker at 6.2 m, tape along the centre line to the back of the grass at 8.8 m](calibration/04-camera-left-6.2m-centre-line-8.8m.jpg)
- [The marker cylinder against a tape, 30 cm](calibration/05-marker-cylinder-30cm.jpg)
- [Cross tape seen from the lawn](calibration/06-cross-tape-from-lawn.jpg)
- [Cross tape looking back towards the camera](calibration/07-cross-tape-looking-back-to-camera.jpg)


## Lawn motion mask

`motion_polygon` in `vps/ground-calibration.json` uses the calibration's
1920×1080 image coordinates. It follows the lawn from the near metal edging
to the foot of the patio steps/wall, inside the left and right bed edges.
The lower-left cutout excludes foreground stems projecting over the lawn;
the narrow far-left strip is excluded because the night still shows a bright
overhanging leaf there. This deliberately leaves the occluded grass out.

Only unknown motion blobs are filtered: their box bottom-centre must be
inside or on the polygon. Detector tracks are unrestricted. The polygon
scales with full-field recording dimensions; initial motion screening is
unchanged. A calibration without `motion_polygon` keeps unmasked fallback.
Existing tracks are unchanged until explicitly re-tracked. Redraw this mask
if the camera moves or plants grow across its boundary.

The numbered vertices on these exact overlays correspond to JSON order;
the 2304×1296 still coordinates are recording coordinates multiplied by 6/5:

- [Day motion-mask overlay](calibration/08-motion-mask-day.jpg)
- [Night motion-mask overlay](calibration/09-motion-mask-night.jpg)

Regenerate both overlays with `.venv/bin/python tests/render_motion_mask.py`.

## Laser survey, 2026-10-04 evening

Ranges from a laser distance measure held at the lens. Heights from a self-levelling line laser whose level line is 9 cm above the centre of the lens; each height is from the ground up to the line at that point. Ground elevation relative to the lens is 9 cm minus that height. The lens is 32.7 cm above the ground directly in front of the camera box. An earlier hand-held 'level' reading against the patio wall (9.9 cm) was not level and is superseded by these.

Pixel positions are the measured spots in the full-sensor still `docs/calibration/` view at 2304x1296; the annotated still is `10-laser-survey-points.jpg`.

| # | Point | Image x, y | Bearing | Range | Line above ground | Ground vs lens | Across | Forward |
|---|---|---|---|---|---|---|---|---|
| 8 | Near stepping stone, right end | 86, 792 | -31.0° | 2.408 m | 47.0 cm | -38.0 cm | -1.22 | 2.04 |
| 7 | Stepping stone, right end | 472, 671 | -21.0° | 3.222 m | 46.0 cm | -37.0 cm | -1.15 | 2.99 |
| 6 | Stepping stone, right end | 679, 601 | -14.9° | 4.279 m | 43.0 cm | -34.0 cm | -1.10 | 4.12 |
| 4 | Right lawn edge, on the edging | 2050, 506 | +26.8° | 4.270 m | 35.0 cm | -26.0 cm | +1.92 | 3.80 |
| 5 | Far stepping stone, right end (the farther of two slabs) | 863, 518 | -9.3° | 6.747 m | 28.5 cm | -19.5 cm | -1.08 | 6.66 |
| 5a | Next stepping stone towards the camera, right end; not marked in the still | | | 6.014 m | 35.0 cm | -26.0 cm | | |
| 9 | Left lawn edge | 161, 581 | -29.2° | 6.775 m | 43.0 cm | -34.0 cm | -3.30 | 5.91 |
| 3 | Far right lawn corner | 1716, 443 | +17.6° | 8.090 m | 19.0 cm | -10.0 cm | +2.45 | 7.71 |
| 1 | Bottom of patio steps, left end | 696, 460 | -14.4° | 9.449 m | 19.0 cm | -10.0 cm | -2.35 | 9.15 |
| 2 | Base of patio wall, centre | 1290, 444 | +4.4° | 9.549 m | 8.8 cm | +0.2 cm | +0.74 | 9.52 |

The lawn rises about 28 cm from the near stepping stones to the far corners, roughly 3 percent, and the right side sits about 8 cm higher than the left at similar distances. The patio wall base is level with the lens, about 10 cm above the far lawn corners. Point 5's pairing was confirmed by the user: the farther slab is 6.747 m with the line 28.5 cm above it, the nearer 6.014 m with 35.0 cm. Point 5a has no marked pixel; locate its right-hand end in the still before using its position, or use its elevation only.

## Physical ground refit, 2026-10-04

The calibration now uses a pinhole camera and one lawn plane. All **17
confirmed positions** (eight bottles and nine laser points, including the
newly confirmed farther slab 5) are used. Point 5a is skipped: without its
bearing or pixel, its elevation cannot be placed on the plane. Focal length
is fixed at 1774 px at 2304×1296, scaled to 1478.333333 px at 1920×1080;
the principal point is (960, 540).

World coordinates are (across, forward, up), in metres. The lens is at
(0, 0, 0.327), with z=0 at the ground directly below it. Ordinary least
squares on the nine laser elevations, adding 0.327 m to lens-relative
heights, gives:

`z = -0.1540128105 + 0.0252214220 * across + 0.0457512974 * forward`

The free intercept extrapolates the lawn 15.4 cm below that local ground
reference at the camera; the lawn fit is not forced through the local ground
point. Elevation residual RMS is 0.026884 m.

Rotation minimizes squared across/forward errors from ray intersections with
this same plane for all 17 positions. Bottles use plane elevations; surveyed
surface variations affect the plane fit rather than introducing separate
surfaces into runtime mapping. Pitch is 6.771199° down, roll 1.431916°
(camera-right axis down), and yaw −0.095472° (right positive). The JSON
records these conventions and all residual vectors. Rays parallel to the
plane, intersecting behind the lens, or landing beyond 12 m forward remain
null. Older calibration files can still use a homography; the production
JSON contains only the physical model.

Ground residuals below are radial distances in metres. The baseline is the
original eight-bottle homography evaluated on all 17 positions. The physical
model has slightly higher RMS and a smaller worst error; the plane and fixed
intrinsics do not remove inconsistencies between the measurements.

| Point | Physical | Old homography |
|---|---:|---:|
| Bottle: tape 2 m | 0.3541 | 0.0532 |
| Bottle: tape 4 m | 0.1095 | 0.2631 |
| Bottle: cross point | 0.2893 | 0.1756 |
| Bottle: middle right | 0.1329 | 0.1290 |
| Bottle: left | 0.6089 | 0.1357 |
| Bottle: rear right | 0.1194 | 0.2468 |
| Bottle: rear left | 0.7739 | 0.2015 |
| Bottle: back centre | 0.2764 | 0.3050 |
| Laser 8 | 0.2287 | 0.3680 |
| Laser 7 | 0.0590 | 0.1411 |
| Laser 6 | 0.2565 | 0.1097 |
| Laser 4 | 0.6686 | 0.7541 |
| Laser 5 | 0.8540 | 0.4467 |
| Laser 9 | 1.1598 | 0.5410 |
| Laser 3 | 0.2976 | 0.3895 |
| Laser 1 | 1.4336 | 1.9673 |
| Laser 2 | 0.5086 | 0.4828 |
| RMS | 0.6109 | 0.5849 |
| Maximum | 1.4336 | 1.9673 |

Plane elevation residuals (fitted minus surveyed), in metres:

| Laser point | Elevation residual |
|---|---:|
| Laser 8 | -0.0385 |
| Laser 7 | -0.0032 |
| Laser 6 | +0.0197 |
| Laser 4 | +0.0013 |
| Laser 5 | -0.0085 |
| Laser 9 | +0.0461 |
| Laser 3 | +0.0335 |
| Laser 1 | -0.0217 |
| Laser 2 | -0.0288 |

Reproduce both fits and residual sets with `.venv/bin/python tests/fit_ground.py`.
