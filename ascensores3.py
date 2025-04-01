import dash
from dash import dcc, html, dash_table, Input, Output
import mysql.connector
import pandas as pd
import plotly.express as px
from datetime import date
import os

# Configuración de conexión a MySQL
host = "192.168.100.60"
user = "zona1"
password = "Sistemas0."
database = "opmt2"

# Ruta del archivo Excel
ruta_excel = os.path.join(os.path.dirname(__file__), "estacionestado.xlsx")
if not os.path.exists(ruta_excel):
    raise FileNotFoundError(f"No se encontró el archivo: {ruta_excel}")

# Obtener datos de MySQL
try:
    conexion = mysql.connector.connect(host=host, user=user, password=password, database=database)
    cursor = conexion.cursor()
    query = """
        SELECT a.nestacion, a.linea, a.codigo_asc, a.fecha_inicial, a.fecha_final, a.observaciones
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
    df_sql = pd.DataFrame(resultados, columns=["nestacion", "linea", "codigo_asc", "fecha_inicial", "fecha_final", "observaciones"])
    df_sql["Estado"] = df_sql["fecha_final"].apply(lambda x: "Inoperativo" if pd.isna(x) or x == "" else "Operativo")

   # Cargar datos desde Excel incluyendo la columna 'nombre'
    df_excel = pd.read_excel(ruta_excel, usecols=["linea", "nestacion", "codigo_asc", "nombre"], engine="openpyxl")

    # Convertir los valores a string y limpiar espacios
    for col in ["linea", "nestacion", "codigo_asc", "nombre"]:
        df_excel[col] = df_excel[col].astype(str).str.strip().str.upper()

    df_sql["linea"] = df_sql["linea"].astype(str).str.strip().str.upper()
    df_sql["nestacion"] = df_sql["nestacion"].astype(str).str.strip().str.upper()
    df_sql["codigo_asc"] = df_sql["codigo_asc"].astype(str).str.strip().str.upper()

    # Unir df_excel con df_sql y asegurarnos de incluir 'nombre'
    df_merged = df_excel.merge(df_sql[["nestacion", "linea", "codigo_asc", "Estado", "fecha_inicial", "fecha_final", "observaciones"]], 
                            on=["nestacion", "linea", "codigo_asc"], how="left")

    df_merged["Estado"] = df_merged["Estado"].fillna("Operativo")
except mysql.connector.Error as err:
    print(f"Error de conexión a la base de datos: {err}")
    df_merged = pd.DataFrame()
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conexion' in locals() and conexion.is_connected(): conexion.close()


    # Renombrar columnas para la tabla
    columnas_renombradas = {
        "linea": "LINEA",
        "nestacion": "ESTACION",
        "codigo_asc": "CÓDIGO ASCENSOR",
        "nombre": "NOMBRE",  # <- Se añade la nueva columna aquí
        "Estado": "ESTADO",
        "fecha_inicial": "FECHA INICIAL",
        "fecha_final": "FECHA FINAL",
        "observaciones": "Observaciones"
    }
    df_merged.rename(columns=columnas_renombradas, inplace=True)

# Función para interrupciones
def obtener_datos(fecha_inicio, fecha_fin, tipo_mant):
    try:
        conexion = mysql.connector.connect(host=host, user=user, password=password, database=database)
        cursor = conexion.cursor()
        cursor.execute("""
            SELECT linea, nestacion 
            FROM ascensores 
            WHERE tipo_mant = %s AND fecha_inicial BETWEEN %s AND %s
        """, (tipo_mant, fecha_inicio, fecha_fin))
        resultados = cursor.fetchall()
        return pd.DataFrame(resultados, columns=["linea", "nestacion"])
    except mysql.connector.Error as err:
        print(f"Error de conexión a MySQL: {err}")
        return pd.DataFrame(columns=["linea", "nestacion"])


app = dash.Dash(__name__, external_stylesheets=["https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css"])
# bg-gray-900 text-white min-h-screen
app.layout = html.Div(className=" p-5", children=[

    html.H1("Dashboard de Ascensores", className="text-center text-3xl font-bold mb-6"),

    html.Div(className="flex flex-wrap -mx-4", children=[

        html.Div(className="w-full lg:w-1/3 px-4 mb-6", children=[
            html.H3("Estado General de Ascensores", className="text-xl font-semibold mb-2"),
            dcc.Graph(id="grafico-general")
        ]),

        html.Div(className="w-full lg:w-2/3 px-4 mb-6", children=[
            html.H3("Tabla de Estados de Ascensores", className="text-xl font-semibold mb-2"),
            dash_table.DataTable(
                id='tabla-ascensores',
                columns=[{"name": i, "id": i} for i in df_merged.columns],
                data=df_merged.to_dict('records'),
                page_size=10,
                filter_action='native',
                style_table={'overflowX': 'auto'},                
                style_cell={'minWidth': '120px', 'maxWidth': '250px', 'whiteSpace': 'normal',                            
                            'textAlign': 'left', 'fontFamily': 'Arial Narrow', 'fontSize': '14px',
                            #'backgroundColor': '#374151', 'color': 'white'
                            },
                style_header={'backgroundColor': '#333333', 'fontWeight': 'bold','fontFamily': 'Arial Narrow', 'fontSize': '15px', 'color': '#ffffff'},
                style_data_conditional=[
                    #{'if': {'filter_query': '{ESTADO} = "Operativo"'}, 'backgroundColor': '#10B981'},
                    {'if': {'filter_query': '{ESTADO} = "Inoperativo"'}, 'backgroundColor': '#EF4444'}
                ]
            )
        ])
    ]),

    html.Div(className="flex flex-wrap -mx-4 mb-6", children=[
        html.Div(className="w-full lg:w-1/2 px-4", children=[
            html.Label("Selecciona una Línea", className="block mb-2"),
            dcc.Dropdown(
                id="filtro-linea",
                options=[{"label": linea, "value": linea} for linea in df_merged["LINEA"].unique()],
                value=df_merged["LINEA"].unique()[0],
                clearable=False
            ),
            html.Div(id="tabla-filtrada", className="mt-4")
        ]),

        html.Div(className="w-full lg:w-1/2 px-4", children=[
            dcc.Graph(id="grafico-estados")
        ])
    ]),
    # bg-gray-800 
    html.Div(className="p-4 rounded-md shadow-md", children=[
        html.H2("Tipos de Mantenimiento por Líneas", className="text-xl font-semibold text-center mb-4"),
        html.Div(className="flex justify-center space-x-4 mb-4", children=[
            dcc.DatePickerRange(
                id="fecha-selector",
                start_date=date(2020, 1, 1),
                end_date=date(2025, 12, 31),
                display_format='DD-MM-YYYY'
            ),
            dcc.Dropdown(
                id="tipo-mant-selector",
                options=[
                    {"label": "Interrupción", "value": "interrupcion"},
                    {"label": "Correctivo", "value": "correctivo"},
                    {"label": "Preventivo", "value": "preventivo"}
                ],
                value="interrupcion",
                clearable=False,
                className="w-48"
            )
        ]),
        dcc.Graph(id="grafico-interrupciones")
    ])
])

# Mantén tus callbacks exactamente igual como estaban antes, no necesitas modificaciones ahí.
@app.callback(
    [Output("grafico-estados", "figure"),
     Output("grafico-general", "figure"),
     Output("tabla-filtrada", "children")],
    [Input("filtro-linea", "value")]
)
def actualizar_graficos_y_tabla(linea):
    df = df_merged[df_merged["LINEA"] == linea] if linea else df_merged
    conteo = df.groupby(["ESTADO", "ESTACION"]).size().reset_index(name="Cantidad")
    fig1 = px.bar(conteo, x="ESTACION", y="Cantidad", color="ESTADO",
                  color_discrete_map={'Operativo': 'green', 'Inoperativo': 'red'}, text="Cantidad")
    fig1.update_traces(textposition='inside', textfont_size=14)

    total = df_merged["ESTADO"].value_counts()
    fig2 = px.pie(values=total.values, names=total.index,
                  color=total.index, color_discrete_map={'Operativo': 'green', 'Inoperativo': 'red'})
    
    tabla = dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in df.columns],
        data=df.to_dict("records"),
        page_size=10,
        style_table={'overflowX': 'auto'},
        filter_action = 'native',
        style_cell={'minWidth': '120px', 'maxWidth': '250px', 'whiteSpace': 'normal',
                    'textAlign': 'left', 'fontFamily': 'Arial Narrow', 'fontSize': '14px',
                    #'backgroundColor': '#1e1e1e', 'color': '#f0f0f0'
                    },
        style_header={'backgroundColor': '#333333', 'fontWeight': 'bold',
                      'fontFamily': 'Arial Narrow', 'fontSize': '15px', 'color': '#ffffff'},
        style_data_conditional=[
            #{'if': {'filter_query': '{ESTADO} = "Operativo"'}, 'backgroundColor': '#006400', 'color': 'white'},
            
            {'if': {'filter_query': '{ESTADO} = "Inoperativo"'}, 'backgroundColor': '#EF4444', 'color': 'white'}
        ]
    )
    return fig1, fig2, tabla

@app.callback(
    Output("grafico-interrupciones", "figure"),
    [Input("fecha-selector", "start_date"),
     Input("fecha-selector", "end_date"),
     Input("tipo-mant-selector", "value")]
)
def actualizar_grafico_interrupciones(fecha_inicio, fecha_fin, tipo_mant):
    df = obtener_datos(fecha_inicio, fecha_fin, tipo_mant)
    if df.empty:
        return px.bar(title="No hay datos disponibles")
    df_grouped = df.groupby(["linea", "nestacion"]).size().reset_index(name="count")
    fig = px.bar(df_grouped, x="linea", y="count", color="nestacion",
                 title=f"Tipo de Mantenimiento - {tipo_mant.capitalize()} ({fecha_inicio} - {fecha_fin})",
                 text="count")
    fig.update_traces(textposition='outside')
    fig.update_layout(title_x=0.5)
    return fig

if __name__ == "__main__":
    app.run(debug=True)