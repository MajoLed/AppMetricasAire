import dash
from dash import html, dcc, Output, Input, callback
import plotly.graph_objects as go
datosmapalat = [6.24, 6.243, 6.2345]
datosmapalon = [-75.37, -75.34, -75.49]
datosmapaaqi = [6.2, 35.6, 34.2]
fig = go.Figure(go.Densitymapbox(lat=[datosmapalat[1]], lon=[datosmapalon[1]], z=[datosmapaaqi[1]],
                                 radius=40, opacity=0.8, zmin=0, zmax=500))
fig.update_layout(mapbox_style="open-street-map", mapbox_center_lon=180)
fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

app = dash.Dash()
app.layout = html.Div([
    dcc.Graph(figure=fig, id="mimapa"),
    dcc.Slider(1,3,1,value=2,id="mislider")
])

@callback(Output('mimapa','figure'),Input('mislider','value'))
def funcioncambio(valorslider): 
    figuralocal = go.Figure(go.Densitymapbox(lat=[datosmapalat[valorslider-1]], lon=[datosmapalon[valorslider-1]], z=[datosmapaaqi[valorslider-1]],
                                 radius=40, opacity=0.8, zmin=0, zmax=500))
    figuralocal.update_layout(mapbox_style="open-street-map")
    figuralocal.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    return figuralocal
app.run_server(debug=True, use_reloader=False, host='0.0.0.0',port=80)