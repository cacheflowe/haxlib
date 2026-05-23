from AppStore import AppStore
from App import App

curState = AppStore.i.GetString(App.i.APP_STATE)
print(f"Current App State: {curState}")

