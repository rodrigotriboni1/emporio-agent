# Empório da Música — Políticas e procedimentos

> Note: Transcribed by hand from `data/politicas_da_loja.pdf` (Manual de
> Políticas e Procedimentos, versão 2.1, junho de 2025). Text stays in
> Portuguese because it is the store's own content. Sections are keyed
> `## [topic]` for the `get_policy` tool. Where the PDF contradicts itself,
> the transcription keeps one value and a `> Note:` explains the choice; see
> also the data-inconsistency table in the README.

## [contact] Sobre a loja e contato

A Empório da Música é uma loja especializada em instrumentos musicais, fundada
em 2008 em Campo Grande, Mato Grosso do Sul. Com mais de 15 anos de atuação,
é referência regional na venda de instrumentos para músicos iniciantes,
intermediários e profissionais. Slogan: "Sua música começa aqui."

Missão: democratizar o acesso a instrumentos musicais de qualidade na região
Centro-Oeste, oferecendo atendimento especializado e preços competitivos,
contribuindo para o desenvolvimento cultural e musical da comunidade.

| Campo | Informação |
|---|---|
| Razão social | Empório da Música Instrumentos Musicais Ltda. |
| Nome fantasia | Empório da Música |
| CNPJ | 12.345.678/0001-90 |
| Endereço | Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333 |
| Telefone | (67) 3341-4444 |
| WhatsApp | (67) 3321-4500 |
| E-mail | contato@emporiodamusica.com.br |
| Fundação | 2008 |

> Note: The PDF lists "Telefone / WhatsApp (67) 3341-4444" in section 1.2, but
> section 7 names (67) 3321-4500 as the WhatsApp channel and the store's main
> remote service channel. The channel-specific rule (section 7) wins for
> WhatsApp; 3341-4444 is kept as the phone line.

> Note: Section 1.2 spells the e-mail with an accent
> (`contato@empóriodamusica.com.br`); the cover page spells it without one.
> The unaccented address is used.

> Note: The PDF says the catalog has "mais de 300 instrumentos"; the product
> data has 65. Do not quote a catalog size.

## [hours] Horário de funcionamento

O atendimento presencial na loja segue os horários abaixo. O atendimento via
WhatsApp segue o mesmo horário, com respostas automáticas fora do expediente.

| Dia | Horário |
|---|---|
| Segunda a sexta-feira | 09:00 às 18:00 |
| Sábado | 09:00 às 13:00 |
| Domingo e feriados | Fechado |

Em datas especiais (Black Friday, Aniversário da Loja, Natal), o horário pode
ser estendido. Alterações são comunicadas com antecedência nas redes sociais e
no atendimento via WhatsApp.

## [payment] Formas de pagamento

Formas aceitas para compras presenciais e online:

| Forma | Condições | Observações |
|---|---|---|
| PIX | Pagamento à vista | 5% de desconto sobre o preço de tabela |
| Cartão de débito | Pagamento à vista | Todas as bandeiras aceitas |
| Cartão de crédito | Até 12x sem juros | Parcela mínima conforme as regras de parcelamento abaixo |
| Boleto bancário | Pagamento à vista | Compensação em até 3 dias úteis |

Regras de parcelamento:

- Parcelamento em até 3x: sem juros, sem valor mínimo de parcela (exceto
  abaixo de R$ 50,00).
- Parcelamento de 4x a 6x: sem juros, parcela mínima de R$ 80,00.
- Parcelamento de 7x a 12x: sem juros, parcela mínima de R$ 100,00.
- Combinação de formas de pagamento (ex.: PIX + cartão): permitida para
  compras acima de R$ 2.000,00.

> Note: The payment table in the PDF says credit card has a "parcela mínima de
> R$ 100,00", which conflicts with the tiered rules. The tiered rules (section
> 3.1) are the specific ones and win; R$ 100,00 is the 7x–12x tier.

> Note: "Exceto abaixo de R$ 50,00" is read as: purchases below R$ 50,00 are
> not split into installments.

> Note: The PIX discount does not apply to prices already on promotion (see
> [promotions]).

## [returns] Trocas e devoluções

A Empório da Música segue as diretrizes do Código de Defesa do Consumidor
(Lei nº 8.078/90) e oferece condições claras para trocas e devoluções.

Direito de arrependimento (compras online):

- O cliente pode solicitar a devolução em até 7 (sete) dias corridos após o
  recebimento do produto, sem necessidade de justificativa.
- O produto deve estar em sua embalagem original, sem sinais de uso, com todos
  os acessórios e manuais.
- O reembolso é realizado na mesma forma de pagamento original em até 10 dias
  úteis.
- O frete de devolução é por conta da loja em caso de arrependimento.

Trocas por defeito:

- Produtos com defeito de fabricação podem ser trocados em até 30 (trinta)
  dias corridos após a compra.
- Após os 30 dias, o cliente deve acionar a garantia diretamente com o
  fabricante. A Empório da Música pode intermediar o processo mediante
  solicitação.
- Danos causados por mau uso, quedas, exposição à umidade excessiva ou
  modificações não autorizadas não são cobertos.

Trocas por preferência:

- Trocas por preferência (cor, modelo, tamanho) são permitidas em até 7 dias,
  mediante disponibilidade do produto desejado.
- O produto deve estar em perfeito estado e na embalagem original.
- Diferenças de valor são cobradas ou reembolsadas conforme o caso.

Itens não elegíveis para troca:

- Instrumentos com personalização ou ajustes sob encomenda (setup, regulagem
  especial).
- Produtos adquiridos em promoções de liquidação com aviso explícito de
  "venda final".
- Boquilhas de instrumentos de sopro, por questões de higiene.

> Note: The order data has no delivered-at date; `estimated_delivery` stands
> in for the delivery date. The start date of the 7-day exchange by preference
> is not stated; delivery is assumed. All orders in the data are treated as
> online purchases.

## [shipping] Frete e entregas

Entregas na região metropolitana de Campo Grande:

- Frete grátis para pedidos acima de R$ 500,00.
- Para pedidos abaixo de R$ 500,00, taxa fixa de R$ 35,00.
- Prazo de entrega: 1 a 3 dias úteis.
- Entrega realizada por motoboy próprio. O cliente é contactado por telefone
  antes da entrega.

Entregas para outras cidades, pelos Correios (PAC e SEDEX) e pela
transportadora Jadlog:

| Modalidade | Prazo estimado | Rastreamento | Seguro |
|---|---|---|---|
| PAC (Correios) | 5 a 12 dias úteis | Sim | Incluído |
| SEDEX (Correios) | 2 a 5 dias úteis | Sim | Incluído |
| Jadlog (.package) | 3 a 8 dias úteis | Sim | Incluído |

O valor do frete é calculado automaticamente com base no CEP de destino, peso
e dimensões do produto. Instrumentos de grande porte (baterias acústicas,
pianos digitais, contrabaixos) podem exigir frete especial com cotação
individual.

Todos os envios incluem seguro contra extravios e danos durante o transporte.
Em caso de avaria, o cliente deve recusar o recebimento e entrar em contato
imediatamente com a loja.

Código de rastreamento: enviado automaticamente por e-mail e WhatsApp assim
que o pedido é despachado. O formato padrão é BR seguido de 9 caracteres
alfanuméricos e BR (exemplo: BR4K7M2X9P1BR). O rastreamento pode ser
consultado diretamente no site dos Correios ou da Jadlog.

> Note: Only Campo Grande is treated as the metropolitan region. An order of
> exactly R$ 500,00 is treated as free shipping. Shipping to other cities is
> never estimated: it needs a CEP quote.

## [promotions] Promoções e descontos

A Empório da Música realiza promoções periódicas ao longo do ano. As
principais campanhas incluem:

- Aniversário da Loja (agosto): descontos de 10% a 25% em itens selecionados.
- Black Friday (novembro): descontos de 15% a 30% em todo o catálogo.
- Volta às Aulas (fevereiro): descontos especiais em instrumentos para
  estudantes.
- Queima de Estoque: promoções pontuais para renovação de catálogo.
- Semana do Músico: promoções na semana do Dia do Músico (22 de novembro).

Regras de promoções:

- Cumulatividade: promoções não são cumulativas. O desconto de PIX (5%) não se
  aplica sobre preços já promocionais.
- Estoque: promoções estão sujeitas à disponibilidade de estoque. Produtos
  esgotados durante a promoção não geram direito a rain check (reserva de
  preço).
- Comunicação: preços promocionais devem sempre ser apresentados junto ao
  preço original e o percentual de desconto, para total transparência ao
  cliente.

Promoção expirada: caso o cliente pergunte sobre uma promoção, verificar se
ela está ativa no sistema. Se estiver vencida, informar com transparência e
apresentar o preço atual. Nunca prometer um desconto que não está mais
vigente.

> Note: Only promotions marked active in the data change a price. Campaign
> names in the data that are not listed above (Páscoa, Liquidação de Inverno,
> Oferta Especial, Desconto Exclusivo) are treated as regular promotions.

## [warranty] Garantia

Garantia legal: conforme o Código de Defesa do Consumidor, todos os produtos
possuem garantia legal de 90 (noventa) dias contra defeitos de fabricação,
contados a partir da data de recebimento pelo cliente.

Garantia do fabricante: além da garantia legal, a maioria dos fabricantes
oferece garantia própria que pode variar de 6 meses a 2 anos. Os prazos e
condições específicos estão no certificado de garantia que acompanha cada
produto.

O que não é coberto pela garantia:

- Desgaste natural de peças (trastes, cordas, feltros, palhetas de sopro).
- Danos por mau uso, queda, exposição a condições climáticas extremas.
- Modificações ou reparos realizados por terceiros não autorizados.
- Danos estéticos que não afetem a funcionalidade do instrumento.

## [privacy] Privacidade e proteção de dados

A Empório da Música está em conformidade com a Lei Geral de Proteção de Dados
(LGPD — Lei nº 13.709/2018). Os dados pessoais coletados durante o atendimento
(nome, telefone, e-mail, endereço) são utilizados exclusivamente para:

- Processamento e entrega de pedidos.
- Comunicação sobre status de pedidos e rastreamento.
- Envio de promoções e novidades (mediante consentimento explícito do
  cliente).
- Cumprimento de obrigações legais e fiscais.

Dados de clientes não são compartilhados com terceiros para fins de
marketing. O cliente pode solicitar a exclusão de seus dados a qualquer
momento entrando em contato pelo WhatsApp ou e-mail.

## [scope] Escopo do atendimento

A loja trabalha exclusivamente com instrumentos musicais: guitarras, baixos,
violões, baterias, teclados, instrumentos de sopro, cordas orquestrais e
ukuleles. Não comercializa acessórios como cordas, palhetas, cabos, cases,
pedais ou amplificadores; pedidos de acessórios devem ser educadamente
redirecionados.

Situações especiais:

- Produto fora de estoque: informar que o produto está temporariamente
  indisponível e sugerir alternativas semelhantes que estejam disponíveis.
  Nunca confirmar disponibilidade sem verificar o estoque atual.
- Produto descontinuado: informar que o produto não faz mais parte do
  catálogo e oferecer modelos equivalentes ou sucessores.
- Reclamação: ouvir o cliente com empatia, registrar a reclamação e
  encaminhar para o responsável. Prazo de retorno: 24 horas úteis.
- Em caso de dúvida sobre a aplicação de qualquer política, consultar a equipe
  antes de responder ao cliente.

> Note: The PDF also says to "sugerir lojas parceiras quando possível", but no
> partner list exists, so no partner store is ever named. Wind and orchestral
> string categories have no products in the data: say nothing is available in
> the system right now rather than "we don't sell it".
