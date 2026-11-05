// An overnight charging schedule for a bus and van depot: 6 electric vehicles, 8 one-hour slots from 22:00 to 06:00.
// Each vehicle plugs in at its arrival slot, must hold its energy need by its departure, and charges at up to 11 kW.
// The depot has 4 chargers (so at most 4 vehicles charge in a slot) and a 40 kW grid connection. Electricity is cheaper after midnight.
// charge[v,t] is the kW vehicle v draws in slot t (one hour, so also kWh); on[v,t] is 1 when it uses a charger in that slot.
param V      = 6;
param T      = 8;
param pmax   = 11;
param chargers = 2;
param grid   = 40;
param price  = [0.30, 0.28, 0.18, 0.12, 0.10, 0.10, 0.14, 0.26];   // per kWh, by slot
param need   = [30, 42, 25, 36, 20, 33];                           // kWh each vehicle must have by departure
// avail[v*T+t] is 1 when vehicle v is plugged in during slot t (arrivals 22:00, 22:00, 23:00, 00:00, 22:00, 01:00; departures 06:00, 04:00, 06:00, 05:00, 03:00, 06:00)
param avail  = [1, 1, 1, 1, 1, 1, 1, 1,
                1, 1, 1, 1, 1, 1, 0, 0,
                0, 1, 1, 1, 1, 1, 1, 1,
                0, 0, 1, 1, 1, 1, 1, 0,
                1, 1, 1, 1, 1, 0, 0, 0,
                0, 0, 0, 1, 1, 1, 1, 1];

var charge[0..V, 0..T] : real 0..11;
var on[0..V, 0..T]     : bool;

minimize cost: sum v in 0..V: sum t in 0..T: price[t] * charge[v,t];

subject to
    forall v in 0..V: energy:   sum t in 0..T: charge[v,t] >= need[v];
    forall v in 0..V: forall t in 0..T: plugged: on[v,t] <= avail[v*T+t];
    forall v in 0..V: forall t in 0..T: link:    charge[v,t] <= 11 * on[v,t];
    forall t in 0..T: chargers_free: sum v in 0..V: on[v,t] <= chargers;
    forall t in 0..T: grid_limit:    sum v in 0..V: charge[v,t] <= grid;
