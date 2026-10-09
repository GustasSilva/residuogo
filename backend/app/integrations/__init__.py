"""Integracoes com APIs publicas de terceiros (IBGE e ViaCEP).

Cada modulo cuida de um servico externo e devolve os dados **ja no formato do
sistema**, nunca o JSON cru do terceiro. Isso mantem o formato da nossa API
estavel mesmo que o do terceiro mude: o ajuste fica em um unico arquivo.

A politica comum - tempo limite, nova tentativa e cache de reserva - esta em
`externo.py`, escrita uma vez e usada pelos dois servicos.
"""
