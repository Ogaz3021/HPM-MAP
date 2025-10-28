import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import geopandas as gpd
import plotly.express as px

# --- Configuración de la Página ---
st.set_page_config(layout="wide", page_title="Dashboard PPD HPM")

st.title('🗺️ Dashboard de Georreferenciación PPD - HPM')
st.caption('Aplicación para la visualización de pacientes (PPD) en la Provincia de Llanquihue.')

# --- Definición de Comunas (para usarla en varios lugares) ---
COMUNAS_LLANQUIHUE = [
    'Puerto Montt', 'Calbuco', 'Cochamó', 'Fresia', 
    'Frutillar', 'Llanquihue', 'Los Muermos', 'Maullín', 'Puerto Varas'
]

# Mapeo para corregir nombres
COMUNA_MAPPING = {
    'Maullin': 'Maullín',
    'Cochamo': 'Cochamó',
    'Rio Negro': 'Río Negro',
    'Hualaihue': 'Hualaihué',
    'Futaleufu': 'Futaleufú',
    'Chaiten': 'Chaitén',
    'Puqueldon': 'Puqueldón'
}

# --- Carga de Datos de PUNTOS (CSV) ---
@st.cache_data
def load_data(csv_file_path):
    try:
        df = pd.read_csv(csv_file_path, sep=';')
    except FileNotFoundError:
        st.error(f"Error: No se encontró el archivo '{csv_file_path}'.")
        return pd.DataFrame()

    df['Comuna'] = df['Comuna'].replace(COMUNA_MAPPING)
    df = df[df['Comuna'].isin(COMUNAS_LLANQUIHUE)].copy()
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lng'] = pd.to_numeric(df['lng'], errors='coerce')
    df.dropna(subset=['lat', 'lng'], inplace=True)
    return df

# --- Carga de FORMAS (GeoJSON) ---
@st.cache_data
def load_shapes(geojson_path):
    try:
        gdf_llanquihue = gpd.read_file(geojson_path)
        gdf_llanquihue = gdf_llanquihue.to_crs(epsg=4326)
        return gdf_llanquihue
        
    except Exception as e:
        st.error(f"Error al cargar el GeoJSON ('{geojson_path}'): {e}")
        st.info("Asegúrate de que 'llanquihue_comunas.geojson' esté en tu repositorio.")
        return None

# --- Cargar los datos ---
DATA_FILE = 'BASE TRABAJO FINAL.xlsx - Sheet1.csv'
SHAPE_FILE = 'llanquihue_comunas.geojson'

df_original = load_data(DATA_FILE)
gdf_comunas = load_shapes(SHAPE_FILE)

if df_original.empty:
    st.warning("No se cargaron datos de PPD. Revisa el archivo CSV.")
    st.stop()

# --- Barra Lateral de Filtros (Sidebar) ---
st.sidebar.header('Panel de Filtros')

# --- REFRESH BUTTON (NUEVO REQUISITO) ---
# Creamos la lógica para el botón de reinicio
if st.sidebar.button("🔄 Reiniciar Vista del Mapa"):
    if 'last_clicked_commune_center' in st.session_state:
        # Borramos el estado guardado del centro para forzar el centro inicial
        del st.session_state['last_clicked_commune_center']
    st.rerun() # Forzamos la recarga de la página

comunas_disponibles = sorted(df_original['Comuna'].unique())
comunas_seleccionadas = st.sidebar.multiselect(
    'Filtrar por Comuna:',
    options=comunas_disponibles,
    default=comunas_disponibles
)

severidad_disponible = sorted(df_original['Ultima registro severidad'].unique())
severidad_seleccionada = st.sidebar.multiselect(
    'Filtrar por Severidad:',
    options=severidad_disponible,
    default=severidad_disponible
)

sexo_disponible = sorted(df_original['Sexo (Desc)'].unique())
sexo_seleccionado = st.sidebar.multiselect(
    'Filtrar por Sexo:',
    options=sexo_disponible,
    default=sexo_disponible
)

st.sidebar.subheader('Filtrar por Tipo de Amputación')
st.sidebar.info("Mostrar PPD que tengan CUALQUIERA de las amputaciones seleccionadas.")

cols_amputacion = [
    'AMP_DEDO_MANO', 'AMP_PULGAR', 'AMP_DEDO_PIE', 'AMP_A_NIVEL_PIE',
    'DESART_TOBILLO', 'AMP_NIVEL_MALEOLO', 'AMP_DEBAJO_RODILLA',
    'DESART_RODILLA', 'AMP_ENCIMA_RODILLA'
]

tipos_amp_seleccionados = []
for col in cols_amputacion:
    if st.sidebar.checkbox(col.replace("_", " ").title()):
        tipos_amp_seleccionados.append(col)

# --- Lógica de Filtrado ---
df_filtrado = df_original[
    (df_original['Comuna'].isin(comunas_seleccionadas)) &
    (df_original['Ultima registro severidad'].isin(severidad_seleccionada)) &
    (df_original['Sexo (Desc)'].isin(sexo_seleccionado))
].copy()

if tipos_amp_seleccionados:
    df_filtrado = df_filtrado[df_filtrado[tipos_amp_seleccionados].sum(axis=1) > 0]


# --- Área Principal: Métricas y Mapa ---
st.metric(label="Total PPD Encontrados", value=len(df_filtrado))

if df_filtrado.empty:
    st.warning("No se encontraron PPD con los filtros seleccionados.")
else:
    lat_media = df_filtrado['lat'].mean()
    lng_media = df_filtrado['lng'].mean()
    
    # Lógica para centrar el mapa en la comuna clicada si existe una en la sesión
    initial_center = [lat_media, lng_media]
    initial_zoom = 9

    if 'last_clicked_commune_center' in st.session_state:
        initial_center = st.session_state['last_clicked_commune_center']
        initial_zoom = 10 

    mapa = folium.Map(location=initial_center, zoom_start=initial_zoom)

    # --- Añadir los Bordes de Comunas (POLÍGONOS) ---
    if gdf_comunas is not None:
        style_comunas = {
            'fillColor': '#222222',
            'color': '#FFFFFF',
            'weight': 1.5,
            'fillOpacity': 0.1
        }
        
        folium.GeoJson(
            gdf_comunas,
            name='Bordes Comunales',
            style_function=lambda x: style_comunas,
            tooltip=folium.GeoJsonTooltip(
                fields=['Comuna_Corregida'], 
                aliases=['Comuna:'],
            ),
            highlight_function=lambda x: {'weight': 3, 'color': 'yellow'},
            popup=folium.GeoJsonPopup(
                fields=['Comuna_Corregida'], 
                aliases=['Comuna:'],
                localize=True
            )
        ).add_to(mapa)

    # --- Creación de Capas de Puntos (Markers) ---
    capas_severidad = {
        'Mayor': folium.FeatureGroup(name='Severidad Mayor', show=True).add_to(mapa),
        'Moderada': folium.FeatureGroup(name='Severidad Moderada', show=True).add_to(mapa),
        'Menor': folium.FeatureGroup(name='Severidad Menor', show=True).add_to(mapa)
    }
    
    colores_severidad = {
        'Mayor': 'red',
        'Moderada': 'orange',
        'Menor': 'green'
    }

    for _, row in df_filtrado.iterrows():
        popup_html = f"""
        <b>Código PPD:</b> {row['Codigo']}<br>
        <b>Comuna:</b> {row['Comuna']}<br>
        <b>Sexo:</b> {row['Sexo (Desc)']}<br>
        <b>Edad:</b> {row['Ultima Edad Registrada']}<br>
        <b>Severidad:</b> {row['Ultima registro severidad']}<br>
        <hr>
        <b>Tiempo a HPM:</b> {row['tiempo (minutos)']:.1f} min<br>
        <b>Distancia:</b> {row['km']:.1f} km<br>
        <b>Total Amputaciones:</b> {row['Total_Amputaciones']}<br>
        """
        popup = folium.Popup(popup_html, max_width=300)
        
        severidad = row['Ultima registro severidad']
        color = colores_severidad.get(severidad, 'gray')
        
        marcador = folium.Marker(
            location=[row['lat'], row['lng']],
            popup=popup,
            tooltip=f"PPD: {row['Codigo']}",
            icon=folium.Icon(color=color, icon='user', prefix='fa')
        )
        
        if severidad in capas_severidad:
            marcador.add_to(capas_severidad[severidad])

    folium.LayerControl().add_to(mapa)

    # --- Mostrar el Mapa y CAPTURAR la interacción del usuario ---
    map_data = st_folium(
        mapa, 
        width=1000, 
        height=600, 
        key=f"map_{len(df_filtrado)}_{initial_zoom}"
    )

    # --- LÓGICA DE CLIC EN COMUNA (GRÁFICO Y TABLA RESUMEN) ---
    try:
        clicked_commune = map_data['last_active_object']['properties']['Comuna_Corregida']
        
        if clicked_commune:
            df_comuna = df_filtrado[df_filtrado['Comuna'] == clicked_commune]
            
            if not df_comuna.empty:
                st.markdown(f"## 📊 Análisis y Resumen de **{clicked_commune}**")
                
                # Opcional: Centrar el mapa en la comuna clicada (guarda el centro para el próximo renderizado)
                center_lat = df_comuna['lat'].mean()
                center_lng = df_comuna['lng'].mean()
                st.session_state['last_clicked_commune_center'] = [center_lat, center_lng]
                # Forzamos la recarga para que el mapa se centre
                st.rerun() 

                # --- 1. Generación del Gráfico de Barras (RE-AGREGADO) ---
                df_chart = df_comuna.groupby('Ultima registro severidad').size().reset_index(name='Total Casos')
                
                fig = px.bar(
                    df_chart,
                    x='Ultima registro severidad',
                    y='Total Casos',
                    color='Ultima registro severidad',
                    title=f'Distribución de Severidad en {clicked_commune}',
                    labels={'Ultima registro severidad': 'Severidad', 'Total Casos': 'Número de Casos'},
                    color_discrete_map={
                        'Mayor': 'red',
                        'Moderada': 'orange',
                        'Menor': 'green'
                    }
                )
                # Ordenar las barras: Menor, Moderada, Mayor
                fig.update_layout(xaxis={'categoryorder':'array', 'categoryarray':['Menor', 'Moderada', 'Mayor']})
                st.plotly_chart(fig, use_container_width=True)

                # --- 2. Cuadro Resumen (Tabla de PPD) ---
                st.subheader(f"📌 {len(df_comuna)} PPD Encontrados en {clicked_commune}")
                
                # Definir columnas de interés para el resumen
                columnas_tabla = [
                    'Codigo', 
                    'Sexo (Desc)', 
                    'Ultima Edad Registrada', 
                    'Ultima registro severidad', 
                    'Total_Amputaciones',
                    'tiempo (minutos)', 
                    'km'
                ]
                
                # Mostrar la tabla de resumen
                st.dataframe(df_comuna[columnas_tabla].rename(columns={
                    'Sexo (Desc)': 'Sexo',
                    'Ultima Edad Registrada': 'Edad',
                    'Ultima registro severidad': 'Severidad',
                    'Total_Amputaciones': 'Amputaciones',
                    'tiempo (minutos)': 'Tiempo HPM (min)',
                    'km': 'Distancia (km)'
                }), use_container_width=True)
                
    except (TypeError, KeyError):
        st.info("Haz clic en una comuna del mapa para ver el análisis de Severidad y la lista de PPD.")
        
    # Opcional: Mostrar la tabla de datos filtrados
    with st.expander("Ver todos los datos filtrados (sin selección de comuna)"):
        st.dataframe(df_filtrado)
