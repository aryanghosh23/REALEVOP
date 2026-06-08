from __future__ import annotations

import pandas as pd

from ev_charging_analytics.transform import build_dimensions, normalize_sessions


def test_normalize_sessions_builds_core_features():
    records = [
        {
            "_id": "abc123",
            "sessionID": "session_1",
            "siteID": "caltech",
            "stationID": "station_1",
            "spaceID": "space_1",
            "clusterID": "garage_a",
            "connectionTime": "Wed, 1 May 2019 15:00:00 GMT",
            "disconnectTime": "Wed, 1 May 2019 18:00:00 GMT",
            "doneChargingTime": "Wed, 1 May 2019 17:00:00 GMT",
            "kWhDelivered": 12.0,
            "timezone": "America/Los_Angeles",
            "userID": "driver_1",
            "userInputs": [
                {
                    "WhPerMile": 280,
                    "kWhRequested": 14,
                    "milesRequested": 50,
                    "minutesAvailable": 180,
                    "modifiedAt": "Wed, 1 May 2019 14:55:00 GMT",
                    "paymentRequired": True,
                    "requestedDeparture": "Wed, 1 May 2019 18:00:00 GMT",
                }
            ],
        }
    ]

    df = normalize_sessions(records)

    assert len(df) == 1
    assert df.loc[0, "session_duration_min"] == 180
    assert df.loc[0, "charging_duration_min"] == 120
    assert df.loc[0, "idle_duration_min"] == 60
    assert df.loc[0, "avg_power_kw"] == 4
    assert df.loc[0, "kwh_requested"] == 14
    assert df.loc[0, "energy_request_gap_kwh"] == 2
    assert isinstance(df.loc[0, "connection_time"], pd.Timestamp)
    assert df.loc[0, "user_id_hash"] is not None


def test_build_dimensions_counts_stations():
    records = [
        {
            "sessionID": "session_1",
            "siteID": "caltech",
            "stationID": "station_1",
            "spaceID": "space_1",
            "connectionTime": "Wed, 1 May 2019 15:00:00 GMT",
            "disconnectTime": "Wed, 1 May 2019 18:00:00 GMT",
            "kWhDelivered": 12.0,
            "timezone": "America/Los_Angeles",
        },
        {
            "sessionID": "session_2",
            "siteID": "caltech",
            "stationID": "station_2",
            "spaceID": "space_2",
            "connectionTime": "Thu, 2 May 2019 15:00:00 GMT",
            "disconnectTime": "Thu, 2 May 2019 16:00:00 GMT",
            "kWhDelivered": 5.0,
            "timezone": "America/Los_Angeles",
        },
    ]

    fact = normalize_sessions(records)
    dim_site, dim_station = build_dimensions(fact)

    assert dim_site.loc[0, "evse_count"] == 2
    assert len(dim_station) == 2

