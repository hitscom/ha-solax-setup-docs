---
title: Pyscripts
tags:
  - documentation
---

### Actual Brain

This part contains the scripts organized by the entities which they use.
First are the EMHASS calls and the SOLAX export limit since they share lot of variables, split into 3 files.
Second is the strategy selector. Please create a folder /config/pyscript with a subfolder /config/pyscript/modules and put the files there:

```
/config/pyscript/em.py                   - the triggers, the calls to EMHASS and the publish watchdog
/config/pyscript/modules/em_inputs.py    - the entity names and the reads from / writes to Home Assistant
/config/pyscript/modules/em_functions.py - the logic, plain Python without Home Assistant or EMHASS
/config/pyscript/strategy.py             - the strategy selector
```

Pyscript only imports from the `modules` folder, so the two `em_*` files have to be there.
Changing a module reloads `em.py` automatically.
There is a todo -> expose the adjustment of the spot_prices to the user by a entity.

#### EMHASS calls

There is not much here also. Just calls to the EMHASS day-ahead optimization and the EMHASS MPC.
Please take a look at https://emhass.readthedocs.io/en/latest/lpems.html#the-emhass-optimizations nice grap.

Goal of these is to provide a plan that updates as the time goes by. You will need to probably adapt the names of the used entities to match your entities.
However, these are ready at the top of `em_inputs.py`, so it should be relatively straightforward.

![Emhass](../assets/emhass.png)

The triggers. Each one reads the values with `em_inputs`, builds an `Optimization` result with `em_functions`
(the EMHASS action, the payload and the reason when it is skipped) and posts it to EMHASS.
The `Optimization` is written to the log as a `repr` before it is posted, so issues with the function code can be found later.
The EMHASS answer is logged the same way:
```python title="/config/pyscript/em.py"
--8<-- "config/pyscript/em.py"
```

The entity names and everything touching Home Assistant. This is the file to adapt to your entities:
```python title="/config/pyscript/modules/em_inputs.py"
--8<-- "config/pyscript/modules/em_inputs.py"
```

The logic. Plain Python, it is covered by the unit tests in the `tests` folder of the repository
(`python3 -m unittest discover -s tests`):
```python title="/config/pyscript/modules/em_functions.py"
--8<-- "config/pyscript/modules/em_functions.py"
```

#### Publish watchdog

`em.py` publishes the EMHASS results to Home Assistant every 5 minutes and right after each optimization.
Every publish EMHASS answers without an error stores its time in `pyscript.emhass_last_publish`.
2 minutes after each publish a check compares that time to now. Less than 15 minutes old is `ok`, otherwise `stale`.
The result is in `pyscript.emhass_publish_watchdog`, with the age in minutes as the `age_minutes` attribute,
so you can use it in an automation or on a dashboard. Both entities are kept across restarts.
The log gets a warning when it turns `stale` and an info when it is `ok` again.

EMHASS answers ok even when it could not write the sensors to Home Assistant, check its log in that case.

```python title="/config/pyscript/em.py"
--8<-- "config/pyscript/em.py:watchdog"
```

#### Solax enable disable

This section is already included in the previous files, but i would just highlight it here.
We are taking look at the spot price and comparing it to user defined sell threshold. Based on that we set the export limit in solax.
Each write to the solax is written to write-limited (100 000 - you probably know), but this happens 2x or 4 times a day max.

The decision:
```python title="/config/pyscript/modules/em_functions.py"
--8<-- "config/pyscript/modules/em_functions.py:export"
```

The trigger writing it to solax:
```python title="/config/pyscript/em.py"
--8<-- "config/pyscript/em.py:export"
```

#### Strategy selector

Honestly this script could be improved quite a bit, but it works for me. I will probably do once I have some energy.

Before trying to understand this, please take a look at the outputs from EMHASS.
Here we are taking a look at the variables the EMHASS give us: https://emhass.readthedocs.io/en/latest/lpems.html#the-emhass-optimizations
This script updates the strategy entity.


This is the script number 2:
```python title="/config/pyscript/strategy.py"
--8<-- "config/pyscript/strategy.py"
```
