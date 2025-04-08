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

def geocode_address(address):
    result = client.pelias_search(text=address)
    features = result.get('features', [])
    if features:
        return features[0]['geometry']['coordinates']  # [lng, lat]
    return None

def get_route_info(start_coords, end_coords):
    route = client.directions(
        coordinates=[start_coords, end_coords],
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
    starting_address = request.form.get('startingAddress', '').strip()
    addresses = []

    manual_input = request.form.get('manualAddresses')
    if manual_input:
        addresses = [line.strip() for line in manual_input.split('\n') if line.strip()]
    else:
        file = request.files.get('file')
        if file and file.filename.endswith('.csv'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            try:
                df = pd.read_csv(filepath)
                if 'Address' in df.columns:
                    addresses = df['Address'].dropna().astype(str).tolist()
                else:
                    return "CSV file does not contain an 'Address' column.", 400
            except Exception as e:
                return f"Error processing file: {str(e)}", 500

    if not addresses or not starting_address:
        return "Missing addresses or starting location", 400

    # Geocode start
    start_coords = geocode_address(starting_address)
    if not start_coords:
        return "Could not geocode starting address.", 400

    # Calculate distances/times
    results = []
    for addr in addresses:
        coords = geocode_address(addr)
        if coords:
            dist, dur = get_route_info(start_coords, coords)
            results.append({
                'address': addr,
                'distance_km': round(dist / 1000, 2),
                'duration_min': round(dur / 60, 1)
            })
            print(f"{addr}: {dist/1000:.2f} km, {dur/60:.1f} min")

    # Pass to result page or display raw
    return render_template('results.html', start=starting_address, results=results)

if __name__ == '__main__':
    app.run(debug=True)
