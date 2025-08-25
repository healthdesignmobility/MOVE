import pandas as pd
import datetime as dt
import pymysql
import yaml
import os

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)

with open("{}/Modules/db_config.yaml".format(script_dir), 'r') as file:
    config = yaml.safe_load(file)
mysql_config = config['mysql']

# Dispatch DF
con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.dispatch;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
dispatch_df = pd.DataFrame(data, columns=["dispatchID", "messageTime", "passengerID", "requestID", "routeIDs", "pickupStationName", "dropoffStationName", "reserveType", "onboardingTime", "dropoffTime", "linkIDs", "pickupStationID", "dropoffStationID", "tripID", "operationID", "vehicleID"])
dispatch_df.to_csv("{}/Modules/data/dispatch_df.csv".format(script_dir), index=False)

# Operation DF
con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.operation;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
operation_df = pd.DataFrame(data, columns=["operationID", "vehicleID", "StationIDs", "routeIDs", "startTime", "endTime", "VehicleType", "operationServiceType"])
operation_df.to_csv("{}/Modules/data/operation_df.csv".format(script_dir), index=False)

# Route DF
con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.route;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
route_df = pd.DataFrame(data, columns=["routeID", "routeSeq", "operationID", "vehicleID", "routeInfo", "linkIDs", "NodeIDs", "originStationID", "originDeptTime", "destinationID", "destDeptTime", "onboardingNum", "dispatchIDs", "lon", "lat", "originBoardingPxIDs", "originGetoffPxIDs", "destBoardingPxIDs", "destGetoffPxIDs"])
route_df.to_csv("{}/Modules/data/route_df.csv".format(script_dir), index=False)

# Request DF
con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.reservation_request;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
request_df = pd.DataFrame(data, columns=["requestID", "passengerID", "messageTime", "pickupStationID", "dropoffStationID", "serviceType", "reserveType", "dispatchID", "responseStatus", "confirmCheck", "passengerCount", "wheelchairCount", "failInfoList", "pickupTimeRequest"])
request_df.to_csv("{}/Modules/data/request_df.csv".format(script_dir), index=False)
