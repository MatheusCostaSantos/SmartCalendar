# Smart Calendar

## O Que É?
O Smart Calendar é uma API criada para a organização de cronogramas, focada na integração direta com o Google Calendário através de um servidor MCP especializado na tarefa de criar eventos.
A criação dessa API foi pensada para organizar automaticamente o calendário com diversos compromissos extraídos de cronogramas com diferentes formatos. O objetivo é padronizar a leitura para todos os formatos compatíveis e automatizar um processo que, manualmente, seria muito demorado.

## Funcionalidades
* A API lê um cronograma em formato PDF, independentemente de como as informações estão apresentadas visualmente, sendo capaz de entender o contexto para cada tipo de cronograma.
* Extrai todos os tipos de eventos e compromissos do PDF, mantendo a estrutura de tabelas e linhas em formato de texto para preservar a organização.
* Envia essas informações para uma IA, que as analisa e utiliza um servidor MCP para se comunicar com a API do Google Calendário e efetivar a criação dos compromissos.
* Para o uso da API e autorização da criação de eventos, foi desenvolvido um aplicativo que direciona o usuário a fazer login em sua conta do Google. A API recebe a chave de acesso (access key) e a utiliza todas as vezes que o usuário fizer uma requisição.

## Ferramentas Usadas

**Backend**
* **FastAPI:** A API em Python que orquestra tudo: recebe o PDF, aciona a IA e expõe o login.

**Inteligência Artificial**
* **OpenAI Agents SDK:** Dá à IA a capacidade de agir (criar os eventos).
* **MCP:** O protocolo que conecta o agente de IA ao serviço que efetivamente se comunica com o Google Calendar.

**Google**
* **OAuth 2.0 (com PKCE):** O padrão de autorização que permite que cada usuário faça login com sua própria conta Google com segurança, garantindo que a API não guarde a senha de ninguém.
* **Google Calendar API:** O serviço do Google onde os eventos são de fato criados.

**Persistência**
* **Azure SQL Database:** Responsável pela persistência dos logins dos usuários, sobrevivendo a possíveis reinicializações do container.

**Deploy**
* **Azure Container Apps:** Ambiente onde a API roda em produção.

**Aplicativo**
* **Kotlin + Jetpack Compose (Android):** O aplicativo cliente utilizado pelo usuário final para consumir essa API.

## Organização da API

### Arquitetura
A API foi desenvolvida utilizando a Arquitetura Limpa (Clean Architecture), organizando as funções em níveis de conhecimento. As camadas exteriores dependem das internas, mas sem a necessidade de saber como elas funcionam, recebendo apenas o resultado final de cada uma. Cada parte foi feita pensando na modularização e em ajustes futuros da API.

O projeto foi organizado em:
* **Domain:** Contratos e interfaces.
* **Data:** Implementações concretas.
* **Service:** Orquestração.
* **Controller:** A porta de entrada HTTP.

Um bom exemplo dessa modularidade é a interface `ExtratorDeCronograma`. Ela obriga que qualquer classe criada para extrair o cronograma tenha um método `extrair`, que retorna uma `string` com as informações. Isso possibilita a troca fácil do extrator de PDFs no futuro, já que o restante da API espera apenas receber uma string com dados, não importando como ela foi extraída internamente.

### Servidor MCP
Pensando em um sistema multiusuários, o servidor MCP não poderia iniciar tendo apenas uma credencial fixa. Para resolver isso, ele foi modificado para receber a credencial do usuário individualmente a cada requisição. Sendo assim, é possível o uso da API por várias pessoas ao mesmo tempo, sem que haja o risco de misturar as credenciais e eventos de contas diferentes.

## Como Funciona

### Autorização
A API não pode simplesmente criar eventos na agenda de qualquer pessoa; ela precisa que cada usuário, individualmente, autorize o acesso à sua própria conta Google. Além disso, a API precisa lembrar posteriormente de qual conta é aquele acesso, para não pedir login toda vez que o usuário for enviar um PDF novo.

Para isso, a API utiliza o OAuth 2.0, um padrão de mercado, que permite ao usuário autorizar aplicações externas a utilizarem a API do seu Google Calendário. Após autorizar, a API recebe um `access_token` e um `refresh_token`, que são guardados em um banco de dados SQL para uso posterior. Em seguida, a API devolve para o aplicativo uma `api_key`, que será a chave exclusiva desse usuário para acessar suas informações no banco de dados.

### Envio e Criação de Eventos
1. O usuário envia um PDF pelo aplicativo através de um endpoint do tipo `POST`, junto com a sua `api_key`.
2. Esse PDF é lido por uma biblioteca Python chamada `pdfplumber`. Essa biblioteca lê o documento caractere por caractere e os agrupa por coordenadas, transformando-os em texto enquanto preserva rigorosamente a estrutura visual de tabelas e linhas.
3. Esse texto estruturado é enviado para um agente de IA, que interpreta o conteúdo pelo contexto e decide quais eventos deve criar na agenda.
4. Como o agente de IA não é capaz de se comunicar diretamente com a API do Google sozinho, ele aciona um servidor MCP especializado, escrito em Node, que realiza a inserção final dos eventos no calendário.

## Como Usar
Para garantir acessibilidade e versatilidade no uso da API, foi criado um aplicativo mobile. Como o projeto ainda está em fase de testes e o escopo de uso não foi verificado publicamente pela Google, é necessário que um dos administradores da API autorize e cadastre previamente o e-mail do usuário no Google Cloud.

1. Instale o APK **SmartCalendar.apk** no seu dispositivo Android.
2. Clique em **Entrar com Google**. (Isso encaminhará você para a página de login do Google, pedindo autorização para modificar o calendário da conta escolhida).
3. Depois de autorizar, você será redirecionado para a página principal do aplicativo.
4. Dentro da página principal, clique em **Escolher PDF**. Isso abrirá o gerenciador de arquivos do seu celular; selecione um cronograma em formato PDF.
5. **(Opcional)** Escreva algo na caixa de texto para complementar as regras do seu cronograma (Exemplo: *"Todas as aulas serão às quartas-feiras, às 12:00"*).
6. Clique em **Enviar** e aguarde a criação dos eventos no seu calendário.