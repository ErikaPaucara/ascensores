import dash
from dash import dcc, html, dash_table, Input, Output
import mysql.connector
import pandas as pd
import plotly.express as px
from datetime import date, datetime
import os

# Configuración de conexión a MySQL
host = "192.168.100.60"
user = "zona1"
password = "Sistemas0."
database = "opmt2"

# Ruta del archivo Excel
ruta_excel = os.path.join(os.path.dirname(__file__), "estacionestado.xlsx")


# Verificar si el archivo Excel existe
if not os.path.exists(ruta_excel):
    raise FileNotFoundError(f"No se encontró el archivo: {ruta_excel}")

# Conectar a la base de datos y obtener datos
try:
    conexion = mysql.connector.connect(
        host=host,
        user=user,
        password=password,
        database=database 
    )
    cursor = conexion.cursor()

    # Consulta SQL
    query = """
        SELECT a.nestacion, a.linea, a.codigo_asc, a.fecha_inicial, a.fecha_final
        FROM ascensores a
        INNER JOIN (
            SELECT nestacion, linea, codigo_asc, MAX(fecha_inicial) AS ultima_fecha
            FROM ascensores
            WHERE tipo_mant = 'interrupcion' AND YEAR(fecha_inicial) = 2025
            GROUP BY nestacion, linea, codigo_asc
        ) ult 
        ON a.codigo_asc = ult.codigo_asc 
        AND a.nestacion = ult.nestacion 
        AND a.linea = ult.linea
        AND a.fecha_inicial = ult.ultima_fecha
        ORDER BY a.linea, a.nestacion, a.codigo_asc;
    """
    
    cursor.execute(query)
    resultados = cursor.fetchall()
    df_sql = pd.DataFrame(resultados, columns=["nestacion", "linea", "codigo_asc", "fecha_inicial", "fecha_final"])

    # Determinar el estado
    df_sql["Estado"] = df_sql["fecha_final"].apply(lambda x: "Inoperativo" if pd.isna(x) or x == "" else "Operativo")

    # Leer el archivo Excel
    df_excel = pd.read_excel(ruta_excel, usecols=["linea", "nestacion", "codigo_asc"], engine="openpyxl")

    # Normalizar texto
    for col in ["linea", "nestacion", "codigo_asc"]:
        df_excel[col] = df_excel[col].astype(str).str.strip().str.upper()
        df_sql[col] = df_sql[col].astype(str).str.strip().str.upper()

    # Comparar datos
    df_merged = df_excel.merge(df_sql[["nestacion", "linea", "codigo_asc", "Estado", "fecha_inicial", "fecha_final"]], 
                               on=["nestacion", "linea", "codigo_asc"], 
                               how="left")
    df_merged["Estado"] = df_merged["Estado"].fillna("Operativo")

    # Eliminar duplicados
    #df_merged = df_merged.loc[df_merged.duplicated(subset=["linea", "nestacion", "codigo_asc"], keep="first") == False]
    # Eliminar duplicados, pero sin afectar "S3" en la línea roja
    df_merged = df_merged.loc[
        (df_merged["linea"] == "ROJA") & (df_merged["nestacion"] == "S3") | 
        ~df_merged.duplicated(subset=["linea", "nestacion", "codigo_asc"], keep="first")
    ]

    
except mysql.connector.Error as err:
    print(f"Error de conexión a la base de datos: {err}")
    df_merged = pd.DataFrame()

finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conexion' in locals() and conexion.is_connected():
        conexion.close()

# Renombrar columnas
columnas_renombradas = {
    "linea": "LINEA",
    "nestacion": "ESTACION",
    "codigo_asc": "CÓDIGO ASCENSOR",
    "Estado": "ESTADO",
    "fecha_inicial": "FECHA INICIAL",
    "fecha_final": "FECHA FINAL"
}

df_merged.rename(columns=columnas_renombradas, inplace=True)

# Función para obtener datos de interrupciones
def obtener_datos(fecha_inicio, fecha_fin, tipo_mant):
    try:
        conexion = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database
        )
        cursor = conexion.cursor()

        query = """
            SELECT linea, nestacion 
            FROM ascensores 
            WHERE tipo_mant = %s 
            AND fecha_inicial BETWEEN %s AND %s
        """
        
        cursor.execute(query, (tipo_mant, fecha_inicio, fecha_fin))
        resultados = cursor.fetchall()
        df = pd.DataFrame(resultados, columns=["linea", "nestacion"])

        cursor.close()
        conexion.close()
        return df

    except mysql.connector.Error as err:
        print(f"Error de conexión a MySQL: {err}")
        return pd.DataFrame(columns=["linea", "nestacion"])

# Crear la app Dash
app = dash.Dash(__name__)

app.layout = html.Div([
    html.Div([html.H1("Estados de Ascensores")], className="header"),

    html.Div([  # Primera fila (Tabla principal y gráfico de torta)
        html.Div([  
            html.H3("Tabla de Estados de Ascensores"),
            dash_table.DataTable(
                id='tabla-ascensores',
                columns=[{"name": columnas_renombradas.get(i, i), "id": i} for i in df_merged.columns],
                data=df_merged.to_dict('records'),
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_data_conditional=[
                    {
                        'if': {'filter_query': '{ESTADO} = "Operativo"'},
                        'backgroundColor': 'lightgreen',
                        'color': 'black'
                    },
                    {
                        'if': {'filter_query': '{ESTADO} = "Inoperativo"'},
                        'backgroundColor': 'lightcoral',
                        'color': 'white'
                    }
                ]
            ),
           
        ], className="tabla-box"),

        html.Div([  
            html.H3("Estado General de Ascensores"),
            dcc.Graph(id="grafico-general"),
            html.H4("Distribución General de Estados", style={'textAlign': 'center'})
        ], className="grafico-torta-box")
    ], className="fila-flex"),

    html.Div([  
        html.Div([  
            html.Label("Selecciona una Línea"),
            dcc.Dropdown(
                id="filtro-linea",
                options=[{"label": linea, "value": linea} for linea in df_merged["LINEA"].unique()],
                value=df_merged["LINEA"].unique()[0] if not df_merged.empty else None,
                clearable=False
            ),
            html.H3("Tabla Filtrada por Línea"),
            html.Div(id="tabla-filtrada")
        ], className="tabla-filtro-box"),

        html.Div([  
            dcc.Graph(id="grafico-estados"),
        ], className="grafico-estados-box")
    ], className="fila-flex"),

    # interrupciones
    html.Div([
        html.H2("Tipo de Mantenimiento por Linea", style={'textAlign': 'center'}),  # Título centrado
        dcc.DatePickerRange(
            id="fecha-selector",
            start_date=date(2020, 1, 1),
            end_date=date(2025, 12, 31),
            display_format='DD-MM-YYYY',
            start_date_placeholder_text='Selecciona Fecha',  
            end_date_placeholder_text='Selecciona Fecha'   
        ),
        dcc.Dropdown(
            id="tipo-mant-selector",
            options=[
                {"label": "Interrupción", "value": "interrupcion"},
                {"label": "Correctivo", "value": "correctivo"},
                {"label": "Preventivo", "value": "preventivo"}
            ],
            value="interrupcion",
            clearable=False
        ),
        dcc.Graph(id="grafico-interrupciones")
    ])
])


@app.callback(
    [Output("grafico-estados", "figure"),
     Output("grafico-general", "figure"),
     Output("tabla-filtrada", "children")],
    [Input("filtro-linea", "value")]
)
def actualizar_graficos_y_tabla(linea_seleccionada):
    #  la línea seleccionada
    df_filtrado = df_merged[df_merged["LINEA"] == linea_seleccionada] if linea_seleccionada else df_merged
    
    # Contar las estaciones operativas  inoperativas
    conteo_estados = df_filtrado.groupby(["ESTADO", "ESTACION"]).size().reset_index(name="Cantidad")
    
    # Crear gráfico de barras
    fig_estado = px.bar(conteo_estados, 
                        x="ESTACION", 
                        y="Cantidad", 
                        color="ESTADO", 
                        color_discrete_map={'Operativo': 'green', 'Inoperativo': 'red'},
                        title="Estado de Ascensores por Línea y Estación",
                        text="Cantidad",
                        labels={'ESTADO': 'Estado', 'Cantidad': 'Cantidad'},
                        category_orders={'ESTADO': ['Operativo', 'Inoperativo']})


    fig_estado.update_traces(textposition='inside', textfont_size=18, textfont_color='white')
    
    # Contar el total de operativos e inoperativos
    conteo_total = df_merged["ESTADO"].value_counts()
    fig_general = px.pie(values=conteo_total.values, names=conteo_total.index, 
                         title="Distribución General de Estados",
                         color=conteo_total.index, color_discrete_map={'Operativo': 'green', 'Inoperativo': 'red'})

    # Asegurarse de que "ESTADO" esté al final de la tabla filtrada
    columnas_filtradas = [col for col in df_filtrado.columns if col != "ESTADO"] + ["ESTADO"]

    # tabla filtrada
    tabla_filtrada = dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in columnas_filtradas],
        data=df_filtrado[columnas_filtradas].to_dict('records'),
        page_size=10,
        style_table={'overflowX': 'auto'},
        style_data_conditional=[
            {
                'if': {'filter_query': '{ESTADO} = "Operativo"'},
                'backgroundColor': 'lightgreen',
                'color': 'black'
            },
            {
                'if': {'filter_query': '{ESTADO} = "Inoperativo"'},
                'backgroundColor': 'lightcoral',
                'color': 'white'
            }
        ]
    )

    return fig_estado, fig_general, tabla_filtrada

@app.callback(
    Output("grafico-interrupciones", "figure"),
    [Input("fecha-selector", "start_date"),
     Input("fecha-selector", "end_date"),
     Input("tipo-mant-selector", "value")]
)
def actualizar_grafico(fecha_inicio, fecha_fin, tipo_mant):
    df = obtener_datos(fecha_inicio, fecha_fin, tipo_mant)
    
    if df.empty:
        return px.bar(title=f"No hay datos para el tipo '{tipo_mant}' en el rango seleccionado")
    
    # Agrupar datos
    df_grouped = df.groupby(["linea", "nestacion"]).size().reset_index(name="count")

    # Crear gráfico
    fig = px.bar(
        df_grouped,
        x="linea",
        y="count",
        color="nestacion",
        title=f"Tipo de Mantenimiento - {tipo_mant.capitalize()} ({fecha_inicio} - {fecha_fin})",
        labels={"count": "Cantidad", "linea": "Línea", "nestacion": "Estación"},
        barmode="group",
        text="count"
    )

    fig.update_traces(textposition='outside')
    fig.update_layout(title_x=0.5)

    return fig

# Ejecutar la app
if __name__ == "__main__":
    app.run(debug=True)
