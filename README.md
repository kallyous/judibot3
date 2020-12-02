# Judibot 3.0

#### Conjunto de bots para coletar documentos jurídicos de diversos tribunais.

##### LaCCAN 2020 - Universidade Federal de Alagoas

---

### **Requisitos:**

* [Python 3](https://www.python.org)
* [Pip](https://pypi.org/project/pip/)
* [Pipenv](https://pipenv.readthedocs.io/en/latest/)
* [Docker](https://www.docker.com/get-started)
* [Splash](https://splash.readthedocs.io/en/stable/)

Com os requisitos instalados, será necessário iniciar um container com o Splash.
O Splash é responsável pela execução do Javascript dás páginas.
Inicie um container com a imagem do Splash com o comando:

```
$ sudo docker run --publish 8050:8050 --detach scrapinghub/splash
```

Isso baixará a imagem [scrapinghub/splash:latest](https://hub.docker.com/r/scrapinghub/splash) do [Docker Hub](https://hub.docker.com/) na primeira vez que for executado. Posteriormente a imagem já salva será reutilizada. Agora um container com Splash deverá estar ouvindo em `localhost:8050` .

Ative o ambiente do pipenv com:

```
$ pipenv install
$ pipenv shell
```

Agora o ambiente virtual está configurado e o terminal está ativado para o uso dos bots.

O arquivo `.env` contém configurações referentes ao banco de dados.

Iniciar o container do Splash e ativar o terminal sempre precisam ser feitos antes de executar algum dos bots. Após a configuração inicial, nas execuções pósteriores será necessário apenas rodar:

```
$ sudo docker run --publish 8050:8050 --detach scrapinghub/splash
$ pipenv shell
```

---

#### Judibot STF

Coleta acórdãos do STF.

Com o terminal ativado e no diretório raiz do projeto, executar:

```
$ python judibot-stf.py --termo "termo de busca"
```

Por exemplo, para pesquisar por "sonegação fiscal", usar `$ python judibot-stf.py --termo "sonegação fiscal"`.

O bot realizará a busca pelo termo fornecido, nas configurações padrão: baixará todos os resultados encontrados, com um timeout de 60 segundos entre os downloads de cada documento.

Para ver descrição de todas as opções, executar:

```
$ python judibot-stf.py --help
```

---
