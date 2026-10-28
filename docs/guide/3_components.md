---
title: Core used components
tags:
  - documentation
---

This section is about setting up required integrations and addons that we will use in next stages.

#### Easy stuff first

Please install the following, they are not really complicated, or special to the integration, so I do no provide much
guidance. You can set sell and buy templates in the Czech Energy Spot Prices Integration to have correct graphs, but the prices are manually adjusted in the pyscripts.

- [HACS](https://www.hacs.xyz/)
- [Advanced Terminal](https://github.com/hassio-addons/addon-ssh/)
- [Solax Modbus](https://github.com/wills106/homeassistant-solax-modbus)
- [Pyscript](https://github.com/custom-components/pyscript)
- [Czech Energy Spot Prices](https://github.com/rnovacek/homeassistant_cz_energy_spot_prices)
- [Weather Forecast](https://github.com/rany2/ha-open-meteo-solar-forecast)

You do not need to setup the Solax much:

- `solax_charger_use_mode` - set to 'Self Use Mode'
- remote control setting leave alone - managed by the automations (later setup)
- `solax_export_control_user_limit` - this will be controlled later by python script, any value is fine

#### Emhass

- [EMHASS](https://github.com/davidusb-geek/emhass)

This is the only integration that we need a bit more. I will go through my setting and explain the rationale.
For full explanations consult [docs](https://emhass.readthedocs.io/en/latest/config.html)

```
EMHASS (Energy Management for Home Assistant) is an optimization tool designed for residential households. The package uses a Linear Programming approach to optimize energy usage while considering factors such as electricity prices, power generation from solar panels, and energy storage from batteries. EMHASS provides a high degree of configurability, making it easy to integrate with Home Assistant and other smart home systems. Whether you have solar panels, energy storage, or just a controllable load, EMHASS can provide an optimized daily schedule for your devices, allowing you to save money and minimize your environmental impact.
```

Emhass will provide us the plan for the the next day. It will use machine learning / statistics to find the energy consumption and
will optimize the usage to maximize the profit.

Let's setup the values.

##### Local
This is quite straightforward.

- `Costfun` will be profit.
- `sensor_power_photovoltaics` is probably solax_pv_power_total
- `sensor_power_photovoltaics_forecast` is the sensor from your weather forecast, for me sensor.energy_production_today_2
- `sensor_power_load_no_var_loads` this needs to be without variable loads, i do not have them, so sensor.solax_house_load
- turn on `continual_publish`
- `logging level` to DEBUG

##### System

- `optimization_time_step` - leave this at 30. I tried 15 minutes, but did not manage to get it working due the forecaster
- `historic_days_to_retrieve` - set to the maximum days you have available in HA or 1 year
- `method_ts_round` - first
- `load_forecast_method` - mlforecaster, i do not have enough data to use typical.
- `weather_forecast_method` - csv, i do not think that this is important, we will anyway pass the data via the rest call.
- `maximum_power_from_grid` - i have the default there
- `maximum_power_to_grid` - depends on the size of your battery, for ideal lifespan it should be ~ 0.2 of capacity. for 11.6 kWh battery, I have it on 3000

##### Tariff
- `load_cost_forecast_method` - csv, i do not think that this is important, we will anyway pass the data via the rest call.
- `production_price_forecast_method` - csv, i do not think that this is important, we will anyway pass the data via the rest call.


##### Deferable loads
- I am not using this

##### Solar System

Turn on this section, but no adjustments are needed

##### Battery

- `weight_battery_discharge` - this is quite important to set, each kWh stored to battery has cost, I recommend 1.5 for the default solax batteries.
- `battery_discharge_power_max` - again same as the maximum_power_to_grid
- `battery_charge_power_max` -  set the same value here, in practise it will anyway take the max from the solar.
- `battery_discharge_efficiency` - 0.95
- `battery_nominal_energy_capacity` - your battery capacity in Wh
- `battery_minimum_state_of_charge` - 0.2 - minimum 20 %, do not set lower, the automation is not perfect and better to keep extra power
- `battery_maximum_state_of_charge` - 0.9 - maximum 90 %, it will probably go to 100% anyway.
- `battery_target_state_of_charge` - 0.7 - the battery capacity at end of day, we will override this from the rest api call based on the next day forecasted power.

#### Configuration.yaml after this stage

This is how your configuration.yaml should look like after this stage:

```yaml

# Loads default set of integrations. Do not remove.
default_config:

# Load frontend themes from the themes folder
frontend:
  themes: !include_dir_merge_named themes

# Allow home assistant to keep more data
recorder:
  purge_keep_days: 100

http:
  use_x_forwarded_for: true
  trusted_proxies:
    # this is for both Cloudflared and EMHASS
    - 172.30.33.0/24

# let's enable this later
# automation: !include_dir_list automations
# script: !include scripts.yaml
# scene: !include scenes.yaml

# setting for the pyscript
pyscript:
  allow_all_imports: true
  hass_is_global: true

logger:
  default: info
  logs:
    # debug logs every call pyscript makes with all its values, turn it on only to chase an issue
    custom_components.pyscript: info
    # the log of em.py, debug adds every publish and every export limit check
    spot_eval: info
```

