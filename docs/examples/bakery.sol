// A bakery has 40 kg of flour, 8 kg of butter and 10 oven hours today.
// Per batch: a loaf needs 2 kg flour, 0.5 kg butter, 1 oven hour and sells for 12;
// a tray of croissants needs 1 kg flour, 1.5 kg butter, 0.5 oven hour and sells for 18.
// A batch can be fractional (half a tray is fine), so this is a linear program.
var loaf   : real 0..20;
var tray   : real 0..20;

maximize sales: 12*loaf + 18*tray;

subject to
    flour:  2*loaf + 1*tray   <= 40;
    butter: 0.5*loaf + 1.5*tray <= 8;
    oven:   1*loaf + 0.5*tray <= 10;
