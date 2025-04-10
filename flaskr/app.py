from flask import Flask, render_template, request
import pandas as pd
import os
import openrouteservice
from sklearn.cluster import KMeans
import numpy as np
from collections import defaultdict

# ORS API key
ORS_API_KEY = '5b3ce3597851110001cf62483c004eed382a4711a74d2f6ff1e07701'
client = openrouteservice.Client(key=ORS_API_KEY)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def geocodeAddress(address):
    result = client.pelias_search(text=address)
    features = result.get('features', [])
    if features:
        return features[0]['geometry']['coordinates']  # [lng, lat]
    return None

def getRouteInfo(startCoords, endCoords):
    route = client.directions(
        coordinates=[startCoords, endCoords],
        profile='driving-car',
        format='geojson'
    )
    segment = route['features'][0]['properties']['segments'][0]
    return segment['distance'], segment['duration']

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    startAddress = request.form.get('startingAddress', '').strip()
    file = request.files.get('file')
    manualInput = request.form.get('manualAddresses')

    if not startAddress:
        return "Missing starting address", 400

    # Geocode the starting address
    startCoords = geocodeAddress(startAddress)
    if not startCoords:
        return "Could not geocode starting address.", 400
    startLng, startLat = startCoords

    rawPoints = []

    # 🟩 Manual input
    if manualInput and not file:
        addresses = [line.strip() for line in manualInput.split('\n') if line.strip()]
        for addr in addresses:
            coords = geocodeAddress(addr)
            if coords:
                lng, lat = coords
                rawPoints.append({'lat': lat, 'lng': lng, 'label': addr})
    # 🟩 CSV input
    elif file and file.filename.endswith('.csv'):
        filePath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filePath)
        try:
            df = pd.read_csv(filePath)
            requiredCols = {'Address', 'City', 'Observed Latitude', 'Observed Longitude'}
            if not requiredCols.issubset(df.columns):
                return "CSV must contain 'Address', 'City', 'Observed Latitude', and 'Observed Longitude' columns.", 400
            df = df.dropna(subset=['Observed Latitude', 'Observed Longitude'])
            df['fullAddress'] = df['Address'].astype(str) + ", " + df['City'].astype(str)
            for _, row in df.iterrows():
                lat, lng = row['Observed Latitude'], row['Observed Longitude']
                label = row['fullAddress']
                rawPoints.append({'lat': lat, 'lng': lng, 'label': label})
        except Exception as e:
            return f"Error processing CSV file: {str(e)}", 500
    else:
        return "Please either upload a valid CSV file or enter manual addresses.", 400

    # Apply K-means clustering
    coordsArray = np.array([[p['lat'], p['lng']] for p in rawPoints])
    kmeans = KMeans(n_clusters=4, random_state=42).fit(coordsArray)

    clusteredRoutes = defaultdict(lambda: {
        'points': [],
        'total_distance_km': 0,
        'total_duration_min': 0
    })

    for i, point in enumerate(rawPoints):
        clusterId = kmeans.labels_[i]
        lat, lng = point['lat'], point['lng']
        label = point['label']
        distance, duration = getRouteInfo([startLng, startLat], [lng, lat])
        clusteredRoutes[clusterId]['points'].append({
            'lat': lat,
            'lng': lng,
            'label': label,
            'distance_km': round(distance / 1000, 2),
            'duration_min': round(duration / 60, 1)
        })
        clusteredRoutes[clusterId]['total_distance_km'] += distance / 1000
        clusteredRoutes[clusterId]['total_duration_min'] += duration / 60

    driverRoutes = []
    mapPoints = []
    for clusterId, route in clusteredRoutes.items():
        driverRoutes.append({
            'driver': f"Driver {clusterId + 1}",
            'points': route['points'],
            'total_distance_km': round(route['total_distance_km'], 2),
            'total_duration_min': round(route['total_duration_min'], 1)
        })
        mapPoints.extend([{**p, 'driver': int(clusterId + 1)} for p in route['points']])

    return render_template('results.html',
                           start=startAddress,
                           driverRoutes=driverRoutes,
                           mapPoints=mapPoints,
                           startLat=startLat,
                           startLng=startLng)

if __name__ == '__main__':
    app.run(debug=True)
