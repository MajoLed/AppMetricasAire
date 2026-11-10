import pandas as pd
import numpy as np

customer_json_file ='Datos_SIATA_Aire_pm25.json'
customers_json = pd.read_json(customer_json_file, convert_dates=True)
latitudes = customers_json.latitud.values.tolist()
longitudes = customers_json.longitud.values.tolist()
fecha = customers_json.datos[1][-1].get('fecha')
m=[]
for i in range(21):
    m.append(customers_json.datos[i][-1].get('valor'))


# en la variable m esta el nivel de la ultima fecha
#creo una malla de 100 x 100 en el area
m=np.array(m)
ysuperior=max(latitudes)
yinferior=min(latitudes)
xinferior=min(longitudes)
xsuperior=max(longitudes)
grid_x, grid_y = np.meshgrid(np.linspace(xinferior,xsuperior,100), np.linspace(yinferior,ysuperior,100))
#construyo la interpolacion
from scipy.interpolate import griddata

grid_z0 = griddata((latitudes, longitudes), m, (grid_y, grid_x), method='nearest')
grid_z1 = griddata((latitudes, longitudes), m, (grid_y, grid_x), method='linear')
grid_z2 = griddata((latitudes, longitudes), m, (grid_y, grid_x), method='cubic')

#llenar los datos NaN con el valor de nearest para completar los datos en z1 y z2
rows = grid_z0.shape[0]
cols = grid_z0.shape[1]

for x in range(0, cols - 1):
    for y in range(0, rows -1):
        if np.isnan(grid_z1[x,y]):
            grid_z1[x,y]=grid_z0[x,y]
        if np.isnan(grid_z2[x,y]):
            grid_z2[x,y]=grid_z0[x,y]
#Graficar los estados
import matplotlib.pyplot as plt
plt.subplot(221)
plt.plot(longitudes, latitudes, 'r.', ms=1)
plt.title('Original')
plt.subplot(222)
plt.contourf(grid_x, grid_y, grid_z0)
plt.plot(longitudes, latitudes, 'r.', ms=1)
plt.colorbar()
plt.title('Mas cercano')
plt.subplot(223)
plt.contourf(grid_x, grid_y, grid_z1)
plt.plot(longitudes, latitudes, 'r.', ms=1)
plt.colorbar()
plt.title('lineal')
plt.subplot(224)
plt.contourf(grid_x, grid_y, grid_z2)
plt.plot(longitudes, latitudes, 'r.', ms=1)
plt.colorbar()
plt.title('cubico')

plt.show()
print(grid_x)