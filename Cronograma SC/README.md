# Cronograma SafetyCulture

Aplicação local para consultar as ocorrências de schedules do SafetyCulture e exportá-las para Excel e CSV.

## Preparação

1. Crie um ambiente Python e instale as dependências: `pip install -r requirements.txt`.
2. Copie `.env.example` para `.env` e defina `SAFETYCULTURE_API_TOKEN`, ou introduza o token apenas na sessão da aplicação.
3. Inicie: `streamlit run app.py`.

O token nunca é guardado pelo programa, exportado ou escrito nos logs. A aplicação consulta o endpoint oficial `GET /scheduling/v1/feed/schedule_occurrences`. O filtro de datas aplica-se a `due_time` e a API pode limitar o histórico disponível; veja a documentação oficial do SafetyCulture para a retenção aplicável à sua organização.

## Campos e mapeamento

São exportados apenas os campos presentes na resposta. `Central` e `UPP` ficam vazios por predefinição, pois não fazem parte do contrato documentado do feed; podem ser preenchidos a partir de dados da organização numa futura integração. O nome da atividade, site e nome do template também dependem de dados adicionais que o feed não garante devolver.

## Separação por cliente

O ficheiro `customer_mapping.csv` relaciona cada local com o respetivo cliente. Pode atualizá-lo quando forem adicionadas centrais ou alteradas atribuições. A aplicação mostra e permite filtrar por `Cliente`; o valor `Não mapeado` sinaliza um local que necessita de ser incluído nesse ficheiro.

## Testes

Execute `pytest` para testar paginação, normalização, erros e exportação sem chamar a API real.

## Publicação no Render

1. Crie um repositório **privado** no GitHub e envie os ficheiros do projeto, sem `.env` nem `.venv`.
2. No Render, selecione **New > Blueprint** e escolha o repositório. O `render.yaml` configura a aplicação.
3. No ecrã de variáveis do serviço, introduza:
   - `SAFETYCULTURE_API_TOKEN`: token da API SafetyCulture;
   - `APP_ACCESS_PASSWORD`: palavra-passe para os utilizadores da aplicação.
4. Publique. O Render atribui uma URL HTTPS.

Nunca envie `.env` ou o token para o GitHub. Em produção, a aplicação usa as variáveis seguras configuradas no Render.
