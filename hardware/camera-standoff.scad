// Camera Module 3 NoIR, standard lens. Dimensions in mm; no libraries.
// https://datasheets.raspberrypi.com/camera/camera-module-3-standard-mechanical-drawing.pdf

/* [Camera: official drawing] */
board_width = 25;
board_height = 23.862;
board_thickness = 1.12;
hole_pitch_x = 21;
hole_pitch_y = 12.5;
hole_edge_y = 2;
lens_y = 14.4;                   // From the edge opposite the ribbon connector.
lens_from_pcb_rear = 11.3 - 2.75; // Inferred overall depth minus rear connector.
lens_front_diameter = 5.75;

/* [Tray] */
tray_extra = 3;                  // Total extra width/length: 1.5 mm per edge.
wall_thickness = 2;
floor_thickness = 2;
camera_stand_height = 5;         // Above the inside floor.
camera_stand_diameter = 4.5;     // Maximum 4.75 mm mounting land.
wall_above_pcb_front = 6;
ribbon_width = 16;
clearance = 0.2;                 // Diametral; ribbon opening gets this per edge.
camera_pilot_diameter = 1.6;     // Tune for the actual self-tapping screw.
camera_pilot_depth = 6;          // Blind: leaves 1 mm of floor beneath the hole.

/* [Enclosure and foot] */
enclosure_depth = 94;
column_extension = 9;           // Measured fit correction: lengthens vertical column.
lens_front_gap = 8.5;            // Nominal gap to height reference; check actual fit.
downward_tilt = 0;               // Fixed in the print, 0 to 20 degrees toward -Y.
grid_pitch = 5;                  // Assumed from discussion; verify before printing.
grid_columns = 4;               // Grid intervals between screw columns.
grid_rows = 4;                  // Grid intervals between screw rows.
base_size = 34;
base_thickness = 4;
base_hole_diameter = 2;          // M2 buttonhead bolts, nuts behind mounting plate.
slot_length = 8;                 // Overall length, along Y.
column_width = 10;

/* [Hidden] */
$fn = 48;
eps = 0.05;
inner_width = board_width + tray_extra;
inner_length = board_height + tray_extra;
outer_width = inner_width + 2 * wall_thickness;
outer_length = inner_length + 2 * wall_thickness;
seat = floor_thickness + camera_stand_height;
rim = seat + board_thickness + wall_above_pcb_front;
hole_rows = [hole_edge_y - board_height / 2,
             hole_edge_y + hole_pitch_y - board_height / 2];
slot_width = base_hole_diameter + clearance;
height_reference = enclosure_depth + column_extension;
seat_z = height_reference - lens_front_gap
         - lens_from_pcb_rear * cos(downward_tilt)
         - lens_front_diameter / 2 * sin(downward_tilt);
tray_z = seat_z - seat * cos(downward_tilt)
         - (lens_y - board_height / 2) * sin(downward_tilt);
flare_run = max(outer_width / 2 - column_width / 2,
                outer_length / 2 * cos(downward_tilt) - column_width / 2);
flare_bottom = tray_z - outer_length / 2 * sin(downward_tilt) - flare_run - clearance;

assert(downward_tilt >= 0 && downward_tilt <= 20 && lens_front_gap > 0,
       "Use 0 to 20 degrees of tilt and positive lens clearance.");
assert(base_size <= 50 && max(outer_width, outer_length) <= 50
       && flare_bottom > base_thickness && column_width >= 8,
       "Holder must fit the enclosure and leave height for a strong column.");
assert(tray_extra >= 2 * clearance && wall_thickness >= 1.6 && floor_thickness >= 2
       && camera_stand_height >= 3 && camera_stand_diameter <= 4.75
       && camera_pilot_diameter > 0
       && camera_stand_diameter > camera_pilot_diameter + 1.6
       && camera_pilot_depth > 0 && camera_pilot_depth <= seat - 1,
       "Keep the PCB and rear components clear and the mounting stands strong.");
assert(ribbon_width + 2 * clearance < inner_width && wall_above_pcb_front > 0,
       "Ribbon opening must leave tray corners intact.");
assert(grid_pitch > 0 && grid_columns >= 1 && grid_rows >= 1
       && grid_columns == floor(grid_columns) && grid_rows == floor(grid_rows)
       && slot_length >= slot_width
       && grid_columns * grid_pitch + slot_width + 4 <= base_size
       && grid_rows * grid_pitch + slot_length + 4 <= base_size
       && grid_columns * grid_pitch - slot_width > column_width,
       "Slots must stay inside the foot with 2 mm edge margins and clear the column.");
assert(tray_z + outer_length / 2 * sin(downward_tilt)
       + rim * cos(downward_tilt) < height_reference,
       "Tray wall exceeds the height reference; reduce tilt or wall height.");

module tray_frame() {
    translate([0, 0, tray_z]) rotate([downward_tilt, 0, 0]) children();
}

difference() {
    union() {
        // Compact foot with four mounting slots cut below.
        linear_extrude(base_thickness)
            hull()
                for (x = [-1, 1], y = [-1, 1])
                    translate([x * (base_size / 2 - 2), y * (base_size / 2 - 2)]) circle(r = 2);
        translate([-column_width / 2, -column_width / 2, base_thickness - eps])
            cube([column_width, column_width, flare_bottom - base_thickness + 2 * eps]);

        // Even the lowest tilted corner has at least 45-degree support below it.
        hull() {
            translate([-column_width / 2, -column_width / 2, flare_bottom])
                cube([column_width, column_width, eps]);
            tray_frame()
                translate([-outer_width / 2, -outer_length / 2, 0])
                    cube([outer_width, outer_length, eps]);
        }
        tray_frame() {
            difference() {
                translate([-outer_width / 2, -outer_length / 2, 0])
                    cube([outer_width, outer_length, rim]);
                translate([-inner_width / 2, -inner_length / 2, floor_thickness])
                    cube([inner_width, inner_length, rim]);
                // Open to the rim on +Y: no bridge above the ribbon bend.
                translate([-(ribbon_width + 2 * clearance) / 2,
                           inner_length / 2 - eps, floor_thickness])
                    cube([ribbon_width + 2 * clearance, wall_thickness + 2 * eps, rim]);
            }
            for (x = [-hole_pitch_x / 2, hole_pitch_x / 2], y = hole_rows)
                translate([x, y, floor_thickness - eps])
                    cylinder(h = camera_stand_height + eps, d = camera_stand_diameter);
        }
    }

    for (x = [-1, 1], y = [-1, 1])
        translate([x * grid_columns * grid_pitch / 2, y * grid_rows * grid_pitch / 2, -eps])
            linear_extrude(base_thickness + 2 * eps)
                hull()
                    for (end = [-1, 1])
                        translate([0, end * (slot_length - slot_width) / 2]) circle(d = slot_width);

    // Blind pilots for self-tapping screws; no holes or pockets in the underside.
    tray_frame()
        for (x = [-hole_pitch_x / 2, hole_pitch_x / 2], y = hole_rows)
            translate([x, y, seat - camera_pilot_depth])
                cylinder(h = camera_pilot_depth + eps, d = camera_pilot_diameter);
}
