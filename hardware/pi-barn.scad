// Pi 4B + PoE HAT light shield; open bottom, solid roof. All dimensions in mm.
// Pi orientation: Ethernet +Y, microSD -Y, USB-C +X, ribbon exits a short end.
// https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-mechanical-drawing.pdf

/* [Body] */
inside_width = 60;
inside_length = 100;
inside_height = 40;              // From mounting plate to underside of roof.
wall = 2;
roof = 2;

/* [Openings: deliberately generous, Pi centred inside] */
usb_center_y = -31.3;
usb_width = 12;                  // Clears the adjacent mounting ear.
usb_height = 24;                 // Notch open to mounting plate.
ethernet_center_x = -17.75;
ethernet_width = 22;
ethernet_height = 26;            // Notch open to mounting plate.
sd_center_x = 0;
sd_width = 24;
sd_height = 12;                  // Notch open to mounting plate.
ribbon_end = -1;                // -Y microSD end; set +1 for Ethernet end.
ribbon_center_x = 16.5;         // CSI plane: 28 - 11.5 mm from Pi drawing.
ribbon_width = 16;
ribbon_height = 2.4;
ribbon_z = 16;                  // Slot centre above mounting plate.

/* [Side ventilation] */
vent_width = 6;
vent_height = 8;                 // Pointed diamonds avoid flat vent ceilings.
vent_pitch = 8;
vent_row_pitch = 10;
vent_margin = 12;                // Keeps vents away from corners and ears.
vent_bottom = 4;
vent_top_margin = 8;             // Solid upper band below the roof.

/* [Mounting] */
grid_pitch = 5;                  // Assumed plate pitch; verify before printing.
bolt_diameter = 2;
buttonhead_diameter = 3.5;
clearance = 0.2;                 // Added to bolt diameter; ribbon gets it per edge.
slot_length = 6;                 // Overall length, along Y.
ear_length = 14;                 // Flush with the ends on the 5 mm grid.
ear_thickness = 3;
ear_edge = 3;                    // Bolt centre to outer edge of ear.
rib_width = 2;

/* [Hidden] */
$fn = 32;
eps = 0.05;
outside_width = inside_width + 2 * wall;
outside_length = inside_length + 2 * wall;
total_height = inside_height + roof;
slot_width = bolt_diameter + clearance;
mount_x = ceil((outside_width / 2 + buttonhead_diameter / 2 + 1) / grid_pitch) * grid_pitch;
mount_y = floor((outside_length / 2 - ear_length / 2) / grid_pitch) * grid_pitch;
ear_extension = mount_x + ear_edge - outside_width / 2;
ribbon_opening = ribbon_width + 2 * clearance;

assert(inside_width >= 60 && inside_length >= 100 && inside_height >= 40
       && wall >= 1.6 && roof >= 1.6, "Keep the requested clear volume and strong walls.");
assert(grid_pitch > 0 && ear_thickness >= 3 && rib_width >= 1.6
       && ear_extension > 0 && slot_length >= slot_width
       && ear_edge > slot_width / 2 + 1
       && slot_length - slot_width + buttonhead_diameter < ear_length - 2 * rib_width,
       "Leave material around the slots and room for buttonheads between the ribs.");
assert(vent_width > 0 && vent_height >= vent_width
       && vent_pitch >= vent_width + 2 && vent_row_pitch >= vent_height + 2
       && vent_bottom >= 2 && vent_top_margin >= 4,
       "Vent diamonds need printable slopes, 2 mm webs and a solid roof border.");
assert(max(usb_height, ethernet_height, sd_height) < inside_height - 4
       && abs(usb_center_y) + usb_width / 2 < inside_length / 2
       && abs(ethernet_center_x) + ethernet_width / 2 < inside_width / 2
       && abs(sd_center_x) + sd_width / 2 < inside_width / 2
       && abs(ribbon_end) == 1
       && abs(ribbon_center_x) + ribbon_opening / 2 < inside_width / 2
       && ribbon_z - ribbon_height / 2 > 0
       && ribbon_z + ribbon_height / 2 < inside_height - 4,
       "Openings must leave corners and the roof intact.");

function near_opening(u, z, centre, width, bottom, height) =
    abs(u - centre) < (width + vent_width) / 2 + 2
    && abs(z - bottom - height / 2) < (height + vent_height) / 2 + 2;

module diamond() {
    linear_extrude(wall + 2 * eps, center = true)
        polygon([[0, vent_height / 2], [vent_width / 2, 0],
                 [0, -vent_height / 2], [-vent_width / 2, 0]]);
}

module barn() {
    difference() {
        union() {
            difference() {
                translate([-outside_width / 2, -outside_length / 2, 0])
                    cube([outside_width, outside_length, total_height]);
                translate([-inside_width / 2, -inside_length / 2, -eps])
                    cube([inside_width, inside_length, inside_height + eps]);
            }
            for (side = [-1, 1], end = [-1, 1]) {
                x = side > 0 ? outside_width / 2 - eps : -mount_x - ear_edge;
                y = end * mount_y - ear_length / 2;
                translate([x, y, 0]) cube([ear_extension + eps, ear_length, ear_thickness]);
                // Two 45-degree ribs support each ear when printed roof-down.
                for (offset = [0, ear_length - rib_width])
                    hull() {
                        translate([side > 0 ? outside_width / 2 - eps : -outside_width / 2,
                                   y + offset, 0])
                            cube([eps, rib_width, ear_thickness + ear_extension]);
                        translate([x, y + offset, 0])
                            cube([ear_extension + eps, rib_width, ear_thickness]);
                    }
            }
        }

        translate([inside_width / 2 - eps, usb_center_y - usb_width / 2, -eps])
            cube([wall + 2 * eps, usb_width, usb_height + eps]);
        translate([ethernet_center_x - ethernet_width / 2, inside_length / 2 - eps, -eps])
            cube([ethernet_width, wall + 2 * eps, ethernet_height + eps]);
        translate([sd_center_x - sd_width / 2, -outside_length / 2 - eps, -eps])
            cube([sd_width, wall + 2 * eps, sd_height + eps]);
        translate([ribbon_center_x - ribbon_opening / 2,
                   ribbon_end > 0 ? inside_length / 2 - eps : -outside_length / 2 - eps,
                   ribbon_z - ribbon_height / 2])
            cube([ribbon_opening, wall + 2 * eps, ribbon_height]);

        for (side = [-1, 1], end = [-1, 1])
            translate([side * mount_x, end * mount_y, -eps])
                linear_extrude(ear_thickness + ear_extension + 2 * eps)
                    hull()
                        for (tip = [-1, 1])
                            translate([0, tip * (slot_length - slot_width) / 2]) circle(d = slot_width);

        for (z = [vent_bottom + vent_height / 2 : vent_row_pitch :
                  inside_height - vent_top_margin - vent_height / 2]) {
            long_count = floor((inside_length - 2 * vent_margin) / vent_pitch);
            for (side = [-1, 1], n = [0 : long_count]) {
                u = (n - long_count / 2) * vent_pitch;
                if (side < 0 || !near_opening(u, z, usb_center_y, usb_width, 0, usb_height))
                    translate([side * (inside_width / 2 + wall / 2), u, z])
                        rotate([90, 0, 90]) diamond();
            }
            short_count = floor((inside_width - 2 * vent_margin) / vent_pitch);
            for (end = [-1, 1], n = [0 : short_count]) {
                u = (n - short_count / 2) * vent_pitch;
                if (((end > 0 && !near_opening(u, z, ethernet_center_x, ethernet_width, 0, ethernet_height))
                    || (end < 0 && !near_opening(u, z, sd_center_x, sd_width, 0, sd_height)))
                    && (end != ribbon_end || !near_opening(u, z, ribbon_center_x, ribbon_opening,
                                                         ribbon_z - ribbon_height / 2, ribbon_height)))
                    translate([u, end * (inside_length / 2 + wall / 2), z])
                        rotate([90, 0, 0]) diamond();
            }
        }
    }
}

// Export ready to print, solid roof on the bed and mounting ears facing up.
translate([0, 0, total_height]) rotate([180, 0, 0]) barn();
