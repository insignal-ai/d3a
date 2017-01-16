# Unit is percentage
MAX_RISK = 100
# Unit is percentage
DEFAULT_RISK = 50
# Unit is degree celsius
MAX_FRIDGE_TEMP = 8.0
# Unit is degree celsius
MIN_FRIDGE_TEMP = 4.0
# Unit is degree celsius
FRIDGE_TEMPERATURE = 7.0
# Unit is cent
MIN_AVERAGE_PRICE = 15
# Unit is in Wh
FRIDGE_MIN_NEEDED_ENERGY = 10
# Unit is kWh
STORAGE_CAPACITY = 0.05
# This price should be just above the marginal costs for a PV system - unit is cent
MIN_PV_SELLING_PRICE = 0.1
# This is the season depended temperature of the earth in 2-3m depth (Between 4C and 10C)
EARTH_TEMP = 6.0
# Unit is degree celsius
MAX_STORAGE_TEMP = 55.0
# Unit is degree celsius
MIN_STORAGE_TEMP = 30.0
# Unit is degree celsius
INITIAL_PUMP_STORAGE_TEMP = 30.0
# Unit is in Wh
PUMP_MIN_NEEDED_ENERGY = 50
# Temperature increment of the storage per min Needed Energy
# Assuming 200L storage capacity and a heat pump conversion efficiency of 5
# --> (1kWh energy = 5kWh heat)
# This means 50 Wh increase the temp of the storage for 0.2C
PUMP_MIN_TEMP_INCREASE = 0.2