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
