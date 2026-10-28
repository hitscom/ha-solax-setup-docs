---
title: Solax Automations
tags:
  - documentation
---


#### Logic

We have a strategy selector updating our helper entity. These automations are realizing the strategy towards the
solax. Remember the Self Use Mode that we are using as setup in the components? That will be our No action strategy.
There are however few cases there we want to hande the invertor with remote control.
If you want to truly understand, please read [docs](https://homeassistant-solax-modbus.readthedocs.io/en/latest/modbus-power-control/).

Handled situations:

- Charging
- Discharge
- Sell to grid
- No action
- Automatic control disabled

#### Configuration.yaml

Uncomment this section.

```yaml
automation: !include_dir_list automations
script: !include scripts.yaml
scene: !include scenes.yaml

```

#### Automations

Create a folder with the automations is /config/automations

=== "`charge.yaml`"
    ```yaml
    --8<-- "config/automations/charge.yaml"
    ```

=== "`discharge.yaml`"
    ```yaml
    --8<-- "config/automations/discharge.yaml"
    ```

=== "`sell_no_store.yaml`"
    ```yaml
    --8<-- "config/automations/sell_no_store.yaml"
    ```

=== "`no_action.yaml`"
    ```yaml
    --8<-- "config/automations/no_action.yaml"
    ```

=== "`disable.yaml`"
    ```yaml
    --8<-- "config/automations/disable.yaml"
    ```

Please setup these automations and you are quite good to go!!!

If you set up the `publish.yaml` automation and the `publish_data` shell command from an earlier version of this guide,
delete both. `em.py` publishes the EMHASS data every 5 minutes and watches that it works, see the [Pyscripts](./5_pyscript.md) page.
With both in place EMHASS gets two publishes at the same moment.


