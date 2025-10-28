import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import geopandas as gpd

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
# ¡Esta función es ahora MUCHO MÁS SIMPLE!
@st.cache_data
def load_shapes(geojson_path):
    try:
        # 1. Cargar el archivo, que ya está filtrado
        gdf_llanquihue = gpd.read_file(geojson_path)
        # 2. Asegurarse de que la proyección sea la correcta
        gdf_llanquihue = gdf_llanquihue.to_crs(epsg=4326)
        return gdf_llanquihue
        
    except Exception as e:
        st.error(f"Error al cargar el GeoJSON ('{geojson_path}'): {e}")
        st.info("Asegúrate de que 'llanquihue_comunas.geojson' esté en tu repositorio.")
        return None

# --- Cargar los datos ---
DATA_FILE = 'BASE TRABAJO FINAL.xlsx - Sheet1.csv'
SHAPE_FILE = 'llanquihue_comunas.geojson' # <-- CAMBIADO

df_original = load_data(DATA_FILE)
gdf_comunas = load_shapes(SHAPE_FILE)

if df_original.empty:
    st.warning("No se cargaron datos de PPD. Revisa el archivo CSV.")
    st.stop()

# --- Barra Lateral de Filtros (Sidebar) ---
st.sidebar.header('Panel de Filtros')

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
    
    mapa = folium.Map(location=[lat_media, lng_media], zoom_start=9)

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
                # El script de Colab se aseguró de que esta columna exista
                fields=['Comuna_Corregida'], 
                aliases=['Comuna:']
            )
        ).add_to(mapa)

    # --- Creación de Capas (por Severidad) ---
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

    # Iterar sobre cada fila del dataframe FILTRADO
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

    # Añadir el control de capas al mapa
    folium.LayerControl().add_to(mapa)

    # --- Mostrar el Mapa en Streamlit ---
    st_folium(mapa, width=1000, height=600)

    with st.expander("Ver tabla de datos filtrados"):
        st.dataframe(df_filtrado)