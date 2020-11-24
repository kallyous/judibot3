# -*- coding: utf-8 -*-

import requests
from lxml import html, etree
from fake_useragent import UserAgent
from w3lib.html import remove_tags
from urllib.parse import urljoin, quote
from pymongo import MongoClient
import click
from pprint import pprint as pp
import re
import math
import zlib
import time

# URL base da página de busca
SITE_HOME = 'https://jurisprudencia.stf.jus.br/'

# Tolerar no máximo essa quantidade de erros de conexão consecutivos.
CONNECTION_ERROR_TOLERANCE = 10

# Usar query = BASE_QUERY.replace('{1}', page_number) para paginação.
# BASE_QUERY = 'pages/search?base={base}&sinonimo=true&plural=true&page={page}&pageSize='+str(BATCH_SIZE)+'&queryString={termo}&sort=_score&sortBy=desc'
BASE_QUERY = 'pages/search?base={base}&pesquisa_inteiro_teor=false&sinonimo=true&plural=true&radicais=false&buscaExata=true&publicacao_data={data_ini}-{data_fim}&page={page}&pageSize={res_pg}&queryString={termo}&sort=_score&sortBy=desc'

# Acha no HTML da página o número de documentos retornados pela busca.
DOC_COUNT_RE = '(\d+\.*\d*) resultado\(s\) para:'

# Acha na URL do documento o ID da ementa, para salvar-mos sem duplicatas.
# DOC_ID_RE = '.*sjur(\d+).*'
DOC_ID_RE = r'search/(\w+-*\w*)/'

# User-Agent aleatório
USER_AGENT = UserAgent().random

# Usa Splash pra processar e rederizar JS. Esse é o script base de acesso.
SPLASH_SCRIPT = "    headers = { ['User-Agent'] = '" + USER_AGENT + """',}
    splash:set_custom_headers(headers)
    splash.private_mode_enabled = false
    splash.images_enabled = false
    assert(splash:go(args.url))
    assert(splash:wait(5))
    return splash:html()
"""

# URL de conexão com cluster do MongoDB.
DB_URL = 'mongodb://judibot-client:U8x3hgZOXHQNQnTs@cluster0-shard-00-00.1re2i.mongodb.net:27017,cluster0-shard-00-01.1re2i.mongodb.net:27017,cluster0-shard-00-02.1re2i.mongodb.net:27017/juri-docs?ssl=true&replicaSet=atlas-egohkf-shard-0&authSource=admin&retryWrites=true&w=majority'

client = None          # Global de conexão com BD.
db = None              # Global pra acessar a conexão aberta.
connection_erros = 0   # Global para rastrear erros de conexão.
timeout = 1            # Global para marcar espera entre acesso a páginas.
data_ini = ''          # Global para data mais antiga de publicação dos docs.
data_fim = None        # Global para data mais recente de publicação dos docs.
res_pg = 50            # Global para quantidade de resultados por página.


def flagConnectionError(sleep_time=15):
    global connection_erros
    connection_erros += 1
    if connection_erros > CONNECTION_ERROR_TOLERANCE:
        print('Problemas na conexão impediram a conclusão da coleta.')
        exit(9)
    time.sleep(sleep_time)


def clearConnectionErrorFlags():
    global connection_erros
    connection_erros = 0


def scrapAcordaoPage(url):
    # Captura id do acórdão.
    doc_id = re.search(DOC_ID_RE, url).group(1)
    
    # Prepara dicionário para segurar os dados coletados.
    document = {'_id': doc_id, 'url': url}
    
    # Carrega página do acórdão usando Splash.
    resp = requests.post(
        url='http://localhost:8050/run',
        json={ 'lua_source': SPLASH_SCRIPT, 'url': url })
    
    # Monta ávore de elementos.
    tree = html.fromstring(resp.content)
    
    # Pega conteúdo da div principal
    main_div = tree.xpath("//div[contains(@class, 'cp-content display-in-print ng-star-inserted')]")[0]
    
    # Se essa div não estiver presente, tivemos erro de conexão.
    if len(main_div) < 1:
        return None  # Como não temos loop aqui dentro, trataremos o erro fora.
    
    # Se tudo ocorreu bem, essa div tem os dados principais do acórdão.
    main_div_raw = etree.tostring(main_div)
    
    # Pegamos o HTML da div, compactamos e incluimos no documento.
    compressed = zlib.compress(main_div_raw, level=9)
    document['raw'] = compressed
    
    # Pega texto da ementa
    ementa = tree.xpath("//h4[text() = 'Ementa']/following-sibling::div/text()")[0]
    if ementa:
        ementa = ' '.join(ementa.split())
        document['ementa'] = ementa
    else:
        document['ementa'] = ''
    
    # Pega texto da decisão
    decisao = tree.xpath("//h4[text() = 'Decisão']/following-sibling::div/text()")[0]
    if decisao:
        decisao = ' '.join(decisao.split())
        document['decisao'] = decisao
    else:
        document['decisao'] = ''
    
    pp(document)
    return document


def buildPaginationURL(termo, base, indice, extras=None):
    termo_enc = quote(termo)   # Encoda termo da busca, escapando espaços e etc.
    indice_str = str(indice)
    if base == 'acordaos':
        return urljoin(SITE_HOME, BASE_QUERY
                       .replace('{base}', base)
                       .replace('{page}', indice_str)
                       .replace('{termo}', termo_enc)
                       .replace('{data_ini}', data_ini )
                       .replace('{data_fim}', data_fim)
                       .replace('{res_pg}', str(res_pg)) )
    else:
        print('Pesquisa por', base, 'não implementado.')
        exit(1)


def retrieveDocUrlList(tree, base):
    urls = []
    if base == 'acordaos':
        # Se retornar vazio, foi erro de conexão, mas tratamos o erro fora.
        a_elems = tree.xpath("//a[contains(@mattooltip, 'Dados completos')]")
        print('Documentos presentes nesta página:', len(a_elems))
        for a in a_elems:
            urls.append(urljoin(SITE_HOME, a.attrib['href']))
    else:
        print('Base', base, 'não implementada.')
    return urls


def scrapDocListByBase(url_docs_list, base):
    docs = []
    list_size = len(url_docs_list)
    i = 0
    if base == 'acordaos':
        while i < list_size:
            url = url_docs_list[i]
            time.sleep(timeout)          # Aguarda tempo definido entre acessos.
            doc = scrapAcordaoPage(url)  # Acessa página e coleta documento.
            
            # Como estamos em um loop, tratamos o erro aqui dentro, se ocorrer.
            if doc:
                docs.append(doc)
                clearConnectionErrorFlags()
                i += 1
            else:
                flagConnectionError()
    else:
        print('Base', base, 'não implementada.')
    print('Documentos obtidos:', len(docs))
    return docs


def updateDatabase(documents, base):
    # Acessa ou cria coleção com o nome da base em questão.
    collection = db[base]
    # Loop com lógica de salvar sem duplicatas.
    for doc in documents:
        # Verifica se o documento já existe.
        exists = collection.find_one({'_id': doc['_id']})
        # Salva caso ainda não conste no BD.
        if not exists:
            print('Documento', doc['_id'], 'é novo, salvando...')
            collection.insert_one(doc)
        else:
            print('Documento', doc['_id'], 'já existe, pulando...')


@click.command()
@click.option('--termo', default='associação ilícita', help='Termo de busca')
@click.option('--espera', default=60, help='Tempo em segundos de espera entre cada documento acessado. Default 60s.')
@click.option('--max-pg', default=0, help='Quantidade máxima de páginas de busca a serem analisadas.')
@click.option('--base', default='acordaos', help='Base de dados do STF onde buscar os documentos: '
              ' acordaos, decisoes-monocr, decisoes-presid, informativos, sumulas, sumulas-vinc, todas')
@click.option('--data-inicial', default='', help='Usar dd-mm-aaaa ou dd/mm/aaaa. Data mais antiga limite de até quando retornar documentos antigos. Default para desde o começo.')
@click.option('--data-final', default=None, help='Usar dd-mm-aaaa ou dd/mm/aaaa. Data recente limite de até quando retornar documentos recentes. Default para data de execução do bot.')
@click.option('--res-por-pag', default=50, help='Quantidade de resultados por página de paginação/resultados da busca. Default 50, recomendado 25, 50 ou 100.')
def scrap(termo, base, espera, max_pg, data_inicial, data_final, res_por_pag):
    global db
    global client
    global timeout
    global data_ini
    global data_fim
    global res_pg
    
    # Ajusta timeout
    timeout = espera
    
    # Data inicial é vazia para pegar desde o começo ou recebida pelo usuário.
    data_ini = data_inicial.replace('-', '').replace('/', '')
    
    # Data final é fornecida pelo usuário ou definida para o dia atual.
    if data_final:
        data_fim = data_final.replace('-', '').replace('/', '')
    else:
        lt = time.localtime(time.time())
        data_fim = f'{lt[2]}{lt[1]}{lt[0]}'
    
    # Define quantidade de resultados por página
    res_pg = res_por_pag
    
    # Abre conexão com banco de dados.
    client = MongoClient(DB_URL)
    
    # Acessa ou cria banco de dados chamado juri-docs no cluster MongoDB.
    db = client['stf-docs']
    
    page_num = 1          # Registra avanço na paginação.
    last_page = 10        # Página de parada, redefinida na primeira iteração.
    
    while page_num <= last_page:
        
        #1 Monta URL da página de busca, contendo a query de busca e paginação.
        url_next_page = buildPaginationURL(termo, base, page_num)
        print('PAGINAÇÂO - URL\n', url_next_page)
        print()
        
        #2 Envia para o Splash processar e rederizar JS, e pega a resposta.
        resp = requests.post(url='http://localhost:8050/run', json={
                                     'lua_source': SPLASH_SCRIPT,
                                     'url': url_next_page })
        tree = html.fromstring(html=resp.content)
        print('SPLASH - RESPOSTA\n\n', ' '.join(remove_tags(resp.text).split()))
        print()
        
        #3 Atualiza last_page se estiver na primeira iteração.
        if page_num == 1:
            
            # Quando max_pg é nãp-positivo, processar até a última página.
            if max_pg < 1:
                match = re.search(DOC_COUNT_RE, remove_tags(resp.text))
                if match:
                    doc_count = match.group(1).replace('.','')
                    doc_count = int(doc_count)
                    last_page = math.ceil(doc_count/res_pg)
                    # Reseta contagem de erros.
                    clearConnectionErrorFlags()
                    
                # Erros de conexão em #1 retornam páginas sem o número de documentos.
                else:
                    flagConnectionError() # Registra erro e aguarda um pouco.
                    continue              # Reinicia iteração atual.
            
            # Quando positivo, essa será a útima página a processar.
            else: last_page = max_pg
        
        print('PAGINAÇÂO - final em', last_page)
        print()
        
        #4 De acordo com a base sendo vasculhada, encontrar e listar URLs dos docs.
        url_docs_list = retrieveDocUrlList(tree, base)
        print('DOCUMENTOS - LISTA DE URL')
        pp(url_docs_list)
        print()
        
        # Erros de conexão na etapa #2 fazem a etapa #4 retornar uma lista vazia.
        if len(url_docs_list) < 1:
            flagConnectionError() # Registra erro e aguarda alguns segundos.
            continue              # Pula o resto das operações e tenta #2 novamente.
        
        #5 Acessar URLs e obter documentos, com rotia adequada para cada base.
        print('DOCUMENTOS - OBJETOS')
        documents = scrapDocListByBase(url_docs_list, base)
        print()
        
        #6 No banco de dados, salvar documentos na coleção da base em questão.
        updateDatabase(documents, base)
        
        # Reseta contagem de erros.
        clearConnectionErrorFlags()
        
        ## Atualiza paginação.
        page_num += 1
        print('PAGINAÇÂO - PRÓX. PG.', page_num)
        print()
        
    # Encerra conexão.
    client.close()


if __name__=='__main__':
    # Executa scrapping
    scrap()

























