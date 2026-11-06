"""DK live: the map of Denmark and northern Germany, power prices, traffic and updates.

Everything comes straight from its source, so the dashboard needs no other container.
Each source is a module with a job that keeps its newest result in memory; the overview
and the map read that. Keys are set up in Admin, and a layer that is off is not fetched."""
from __future__ import annotations

from ...core.sections import Section
from . import (airports, alarms, autobahn, client, dmi, energy, flights, forecast, niord, police, ships, store, traffic,
               trains, weather, webcams)
from .routes import router

SECTION = Section(
    id="dklive",
    title="DK live",
    router=router,
    migrations=[(1, "live cache", store.migrate_1)],
    overview=client.overview,
    jobs=[
        (15.0, flights.job), (1.5, flights.route_job),
        (15.0, ships.job),
        (90.0, alarms.job), (600.0, alarms.stations_job), (1.5, alarms.geocode_job),
        (180.0, traffic.job),
        (60.0, trains.job),
        (300.0, autobahn.job), (1800.0, autobahn.camera_job),
        (3600.0, webcams.job),
        (300.0, weather.radar_job), (120.0, weather.lightning_job),
        (600.0, dmi.wind_job), (600.0, dmi.sea_job),
        (900.0, niord.job),
        (120.0, energy.now_job), (300.0, energy.price_job),
        (600.0, forecast.job),
        (300.0, police.job),
        (600.0, airports.job),
    ],
    setup=client.setup_status,
    sources=client.sources,
    reset=client.reset,
)
