// Spacer for the original-height camera stand. Dimensions in mm; no libraries.
height = 9;
base_size = 34;
corner_radius = 2;
grid_pitch = 5;
grid_columns = 4;
grid_rows = 4;
bolt_diameter = 2;
clearance = 0.2;
slot_length = 8;

/* [Hidden] */
$fn = 48;
eps = 0.05;
slot_width = bolt_diameter + clearance;
assert(height > 0 && corner_radius > 0 && base_size > 2 * corner_radius);
assert(grid_pitch > 0 && grid_columns >= 1 && grid_rows >= 1
       && grid_columns == floor(grid_columns) && grid_rows == floor(grid_rows));
assert(slot_width > 0 && slot_length >= slot_width
       && grid_columns * grid_pitch + slot_width + 4 <= base_size
       && grid_rows * grid_pitch + slot_length + 4 <= base_size);

difference() {
    linear_extrude(height)
        hull()
            for (x = [-1, 1], y = [-1, 1])
                translate([x * (base_size / 2 - corner_radius),
                           y * (base_size / 2 - corner_radius)]) circle(r = corner_radius);
    for (x = [-1, 1], y = [-1, 1])
        translate([x * grid_columns * grid_pitch / 2, y * grid_rows * grid_pitch / 2, -eps])
            linear_extrude(height + 2 * eps)
                hull()
                    for (end = [-1, 1])
                        translate([0, end * (slot_length - slot_width) / 2]) circle(d = slot_width);
}
