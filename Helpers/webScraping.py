import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin
import os
import re  # <--- IMPORTANTE: Agregamos esto para leer los nombres correctamente
from typing import List, Dict
from werkzeug.utils import secure_filename
from .funciones import Funciones 

class WebScraping:
    """Clase para realizar web scraping a la Superfinanciera (Versión Producción)"""
    
    def __init__(self, dominio_base: str = "https://www.superfinanciera.gov.co"):
        self.dominio_base = dominio_base
        self.session = requests.Session()
        # Headers robustos iguales a los de tu prueba exitosa
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })

    def extract_links(self, url: str, listado_extensiones: List[str] = None) -> List[Dict]:
        """Extrae links detectando PDFs y loader.php"""
        if listado_extensiones is None:
            listado_extensiones = ['pdf', 'aspx']
        
        try:
            print(f"🔎 Analizando: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser') # Usamos html.parser que es más estándar
            container_div = soup.body 
            
            links = []
            if container_div:
                for link in container_div.find_all('a'):
                    href = link.get('href')
                    if href:
                        full_url = urljoin(url, href)
                        
                        # Filtro de dominio
                        if full_url.startswith(self.dominio_base):
                            
                            for ext in listado_extensiones:
                                ext_lower = ext.lower().strip()
                                
                                # Lógica para detectar descargas ocultas o directas
                                es_loader = 'loader.php' in full_url and 'descargar' in full_url
                                
                                if f'.{ext_lower}' in full_url.lower() or (ext_lower == 'pdf' and es_loader): 
                                    
                                    titulo = link.get_text(strip=True)
                                    if not titulo: titulo = "Documento sin título"

                                    links.append({
                                        'url': full_url,
                                        'type': ext_lower,
                                        'titulo': titulo
                                    })
                                    break 
            return links
            
        except Exception as e:
            print(f"❌ Error procesando {url}: {e}")
            return []
    
    def descargar_pdfs(self, json_file_path: str, carpeta_destino: str = "static/uploads") -> Dict:
        """Descarga PDFs usando la lógica probada de detección de nombres"""
        try:
            all_links = self._cargar_links_desde_json(json_file_path)
            pdf_links = [l for l in all_links if l.get('type') == 'pdf']
            
            if not pdf_links:
                return {'success': True, 'mensaje': 'No hay PDFs', 'descargados': 0}
            
            Funciones.crear_carpeta(carpeta_destino)
            print(f"🧹 Limpiando carpeta: {carpeta_destino}")
            Funciones.borrar_contenido_carpeta(carpeta_destino)
            
            descargados = 0
            errores = 0
            
            print(f"⬇️ Iniciando descarga de {len(pdf_links)} archivos...")
            
            for i, link in enumerate(pdf_links, 1):
                pdf_url = link['url']
                titulo_doc = link.get('titulo', f'documento_{i}')
                
                try:
                    # Petición al archivo
                    response = self.session.get(pdf_url, stream=True, timeout=60)
                    response.raise_for_status()
                    
                    nombre_final = ""
                    
                    # --- LÓGICA DE LA PRUEBA EXITOSA ---
                    # 1. Intentar leer Content-Disposition con expresiones regulares
                    if "Content-Disposition" in response.headers:
                        cd = response.headers["Content-Disposition"]
                        # Busca texto entre comillas después de filename=
                        nombres = re.findall('filename="?([^"]+)"?', cd)
                        if nombres:
                            nombre_final = nombres[0]
                            
                            # Corrección de tildes (Arregla "InclusiÃ³n")
                            try:
                                nombre_final = nombre_final.encode('iso-8859-1').decode('utf-8')
                            except:
                                pass # Si falla, dejamos el nombre como vino
                    
                    # 2. Si falló, usar el Título del enlace
                    if not nombre_final or "loader.php" in nombre_final:
                        nombre_limpio = "".join([c if c.isalnum() else "_" for c in titulo_doc])
                        nombre_final = f"{nombre_limpio}.pdf"
                    
                    # 3. Limpieza final y asegurar extensión
                    nombre_final = secure_filename(nombre_final)
                    if not nombre_final.lower().endswith('.pdf'):
                        nombre_final += ".pdf"

                    ruta_archivo = os.path.join(carpeta_destino, nombre_final)
                    
                    print(f"   ✅ [{i}] Guardando: {nombre_final}")
                    
                    with open(ruta_archivo, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                    descargados += 1
                    
                except Exception as e:
                    errores += 1
                    print(f"   ❌ Error en {titulo_doc}: {e}")
            
            return {'success': True, 'total': len(pdf_links), 'descargados': descargados, 'errores': errores}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # --- Métodos Auxiliares ---
    def extraer_todos_los_links(self, url_inicial, json_file_path, listado_extensiones=None, max_iteraciones=1):
        links = self.extract_links(url_inicial, listado_extensiones)
        self._guardar_links_en_json(json_file_path, {"links": links})
        return {'success': True, 'total_links': len(links), 'links': links}

    def _cargar_links_desde_json(self, json_file_path):
        if os.path.exists(json_file_path):
            try:
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get("links", [])
            except: return []
        return []
    
    def _guardar_links_en_json(self, json_file_path, data):
        try:
            os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except: pass

    def close(self):
        self.session.close()