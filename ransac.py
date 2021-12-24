import datetime as dt
import json
from IPython.display import display
from sklearn import datasets
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression, RANSACRegressor
from sklearn.metrics import r2_score, mean_squared_error
import numpy as np
import pandas as pd

def avg_price(row):
    return (row['h'] + row['l'])/2

def current_time_index():
    # MIGHT HAVE TO CHANGE TIME ZONE
    # calculate number of 15-minute increments that have passed since market open
    # = mins since 9:30 am if it is a weekday // 15
    now = dt.datetime.now()
    today = dt.datetime.today()
    mkt_open = dt.datetime(today.year, today.month, today.day, hour=8, minute=30)
    difference = (now - mkt_open)
    total_seconds = difference.total_seconds()
    # 900 = 15 * 60 sec
    return total_seconds // 900

def slope(r):
    # convert to df
    bars = json.loads(r.text)['bars']
    df = pd.DataFrame(bars)
    df['p'] = df.apply (lambda row: avg_price(row), axis=1)
    # change to format for ransac
    X = df.index.values.reshape(-1, 1)
    y = df['p'].to_numpy().reshape(-1, 1)

    ransac = RANSACRegressor(LinearRegression(),residual_threshold=3,random_state=0)
    ransac.fit(X, y)
    fifteens = current_time_index()
    prediction2=ransac.predict([[fifteens + df.shape[0]]])
    # check that the second thing is right
    return [prediction2[0][0], ransac.estimator_.coef_]

    



        

