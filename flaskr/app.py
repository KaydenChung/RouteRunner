from flask import Flask, render_template, request
import pandas as pd
import os
import openrouteservice

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

    mapPoints = []
    results = []

    # 🟩 Manual input case
    if manualInput and not file:
        addresses = [line.strip() for line in manualInput.split('\n') if line.strip()]
        for addr in addresses:
            coords = geocodeAddress(addr)
            if coords:
                lng, lat = coords
                distance, duration = getRouteInfo([startLng, startLat], [lng, lat])

                results.append({
                    'address': addr,
                    'distance_km': round(distance / 1000, 2),
                    'duration_min': round(duration / 60, 1)
                })

                mapPoints.append({'lat': lat, 'lng': lng, 'label': addr})
            else:
                print(f"Could not geocode address: {addr}")

    # 🟩 CSV input case
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
            df['lat'] = df['Observed Latitude']
            df['lng'] = df['Observed Longitude']

            for _, row in df.iterrows():
                lat, lng = row['lat'], row['lng']
                label = row['fullAddress']

                distance, duration = getRouteInfo([startLng, startLat], [lng, lat])

                results.append({
                    'address': label,
                    'distance_km': round(distance / 1000, 2),
                    'duration_min': round(duration / 60, 1)
                })

                mapPoints.append({'lat': lat, 'lng': lng, 'label': label})

        except Exception as e:
            return f"Error processing CSV file: {str(e)}", 500

    else:
        return "Please either upload a valid CSV file or enter manual addresses.", 400

    # Render the map results
    return render_template('results.html',
                           start=startAddress,
                           results=results,
                           mapPoints=mapPoints,
                           startLat=startLat,
                           startLng=startLng)

if __name__ == '__main__':
    app.run(debug=True)
