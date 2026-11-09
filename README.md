# cascadia-bot

Cascadia masa oyununun **kurallarını birebir uygulayan, arayüzsüz (headless) bir oyun motoru** ve
farklı bot algoritmalarını karşılaştırmak için bir test ortamı. Saf Python (3.10+), bağımlılık yok
(testler için `pytest`).

```bash
python -m pytest -q                                              # testler
python -m cascadia_bot.arena random greedy heuristic --games 200 --workers 4
python -m cascadia_bot.arena greedy heuristic --solo --games 100   # solo kıyas
python -m cascadia_bot.arena greedy lookahead --cards ABCDA --games 1 --show
```

## Uygulanan kurallar

Kaynak: resmi kural kitabı (AEG / Flatout Games) ve tasarımcı Randy Flynn'in BGG/FAQ açıklamaları.
Kural kitabında açıkça yazmayan yorumlar aşağıda **(açıklama)** olarak işaretlendi.

**Bileşenler** – 85 habitat karosu (25 keystone: her habitattan 5; 60 çift habitatlı: 10 habitat
çiftinin her birinden 6), 5 başlangıç karosu (her biri 3 hex), 100 hayvan jetonu (her türden 20),
doğa jetonları. Karo verisinde her hayvan tam 32 karoda, her habitat 29 kez geçer.

**Kurulum** – 20 × oyuncu + 3 karo (solo: 43). Her hayvan için rastgele A–D puan kartı (veya
aile/orta seviye varyantı). Ortada 4 karo + 4 jeton çifti.

**Tur**
1. Aşırı nüfus: ortadaki 4 jeton aynıysa otomatik silinir (gerekirse tekrar). Tam 3 jeton aynıysa
   oyuncu isterse bu 3'ünü silebilir – turda **en fazla bir kez**, doğa jetonuyla silmeden sonra da
   yapılabilir **(açıklama)**. Silinen jetonlar kenara konur, tüm silmeler bitince torbaya döner.
2. Doğa jetonu (sınırsız sayıda): istediğin jetonları sil-yeniden çek **veya** herhangi bir karoyu
   herhangi bir jetonla al.
3. Karoyu ortamına komşu bir boş hex'e herhangi bir yönde koy. Jetonu, üzerinde jeton olmayan ve o
   hayvanı gösteren bir karoya koy (yeni karo dahil) ya da torbaya geri at. Keystone karoya jeton
   koymak 1 doğa jetonu kazandırır (başlangıç karosunun keystone kısmı dahil).
4. Boşalan yerleri doldur (kaydırma yok). **Solo:** önce desteden en uzak karo ve jeton oyundan
   çıkarılır, kalanlar kaydırılır, 2 yeni çekilir.
5. Desteden karo çekilemediğinde oyun biter → herkes tam 20 tur oynar.

**Puanlama** – hayvan kartları + her habitatın en büyük bitişik koridoru (kenarlar aynı habitat
olmalı) + çoğunluk bonusları + kalan doğa jetonları (1'er puan). Beraberlikte çok doğa jetonu olan
kazanır.

- Çoğunluk: solo 7+ koridor → +2; 2 oyuncu: en büyük +2, eşitlik 1'er; 3–4 oyuncu: en büyük +3,
  ikinci +1; ilk sırada ikili eşitlik 2'şer (ikinciye yok), üçlü/dörtlü eşitlik 1'er; ikincilikte
  eşitlik 0.

| Kart | Ayı | Geyik | Somon (koşu) | Şahin | Tilki |
|---|---|---|---|---|---|
| A | tam 2'li grup sayısı: 1→4, 2→11, 3→19, 4+→27 | düz çizgi 1–4: 2/5/9/13 (uzun çizgi en iyi şekilde bölünür) | 1..7+: 2/5/8/12/16/20/25 | başka şahine komşu olmayan şahin sayısı 1..8+: 2/5/8/11/14/18/22/26 | her tilki: komşu farklı tür sayısı (tilki dahil) 1..5 |
| B | tam 3'lü grup: 10'ar | tek 2, çift 5, üçgen 9, eşkenar dörtgen 13 | 1..5+: 2/4/9/11/17 | komşusuz **ve** görüş hattı olan şahin 2..8+: 5/9/12/16/20/24/28 (1 → 0) | her tilki: komşu farklı hayvan çifti (tilki hariç) 1/2/3 → 3/5/7 |
| C | 1/2/3'lük gruplar 2/5/8, her tam set (+1,+2,+3) için +3 **(açıklama: tekrar kazanılabilir)** | her bitişik grup 1..8+: 2/4/7/10/14/18/23/28 | 3/4/5+ → 10/12/15 | her görüş hattı 3 puan | her tilki: en bol komşu (tilki olmayan) türün adedi |
| D | 2/3/4'lük gruplar 5/8/13 | ortak bir merkezi çevreleyen (kısmi) halka 1..6: 2/5/8/12/16/21 **(açıklama: boşluklu olabilir)** | 3+ koşu: somon başına 1 + koşuya komşu her hayvan jetonu 1 **(açıklama: en az 3)** | görüş hattı olan şahin çiftleri, aradaki farklı tür 1/2/3+ → 4/7/9, her şahin tek çiftte | tilki çifti: çevresindeki 8 hex'te farklı hayvan çifti 1..4 → 5/7/9/11 |

Ek kurallar ve açıklamalar:
- Ayı grupları tam boyutta olmalı; başka boyuttaki gruplar 0 puan.
- Geyik: her geyik tek bir formasyonda sayılır; en yüksek puanlı yorum seçilir (tam arama).
- Somon koşusu: her somon en fazla 2 somona komşu. 3+ somona komşu bir somon hiçbir koşuya ait
  olmaz, kalanlar koşu olarak sayılır **(açıklama)**.
- Görüş hattı: düz çizgi, yalnızca araya giren başka bir şahin keser; **komşu şahinler** birbirine
  görüş hattı oluşturmaz **(açıklama)**. Şahin B'de yalnızca puanlanan şahinin komşusuz olması gerekir.
- Tilki B/D: aynı türden 3+ hayvan yine tek çift sayılır; tilki D'de her tilki tek çiftte.
- Aile varyantı: her tür için grup 1/2/3+ → 2/5/9. Orta seviye: 2/3/4+ → 5/8/12.

## Kod yapısı

```
cascadia_bot/
  components.py   habitatlar, hayvanlar, 85 karo + 5 başlangıç karosu
  hexgrid.py      eksenel (q, r) hex koordinatları
  board.py        oyuncu ortamı: karo/jeton yerleştirme, koridorlar (artımlı hesap)
  scoring.py      tüm puan kartları (A–D ×5, aile, orta seviye), çoğunluk, toplam
  game.py         oyun durumu ve tur akışı (aşırı nüfus, doğa jetonu, solo, oyun sonu)
  runner.py       botlarla tek oyun oynatma
  arena.py        turnuva / CLI (koltuk rotasyonu, paralel işlem, JSON çıktı)
  render.py       metin tabanlı tahta çıktısı
  bots/           random, greedy, heuristic, lookahead (Monte Carlo)
tests/            puan kartları ve kural testleri
```

## Kendi botunu yazmak

```python
from cascadia_bot.bots import Bot, register
from cascadia_bot.bots.evaluation import evaluate_candidates
from cascadia_bot.game import Placement

class MyBot(Bot):
    name = "mybot"

    def choose_pre_action(self, game):
        # None -> taslak seçimine geç; ya da WipeOverpopulation() / NatureWipe((0, 2))
        return None

    def choose_placement(self, game) -> Placement:
        # game.draft_options(), game.legal_placements(), game.board, game.cards ...
        cands = evaluate_candidates(game, rng=self.rng)
        return max(cands, key=lambda c: c.value).placement

register("mybot", MyBot)
```

Sonra `python -m cascadia_bot.arena mybot greedy --plugin my_bots` (`my_bots.py` botu kaydeden modül;
`--workers` > 1 ile kullanırken modül alt süreçlerde de import edilebilir olmalı) ya da doğrudan Python'dan:

```python
from cascadia_bot import GameConfig, ScoringCards, play_game
from cascadia_bot.bots import make_bot
res = play_game([MyBot(seed=1), make_bot("greedy", seed=2)],
                GameConfig(num_players=2, seed=7, cards=ScoringCards.from_string("ABCDA")))
print(res.totals, res.winners)
```

Botlar canlı `Game` nesnesini alır; gizli bilgiye (`game.tile_stack` sırası, torba RNG'si) bakmamalı.
Simülasyon için `game.determinize(rng)` gizli bilgiyi yeniden örnekleyen bağımsız bir kopya döndürür.

### Hazır botlar

| Bot | Fikir |
|---|---|
| `random` | rastgele yasal hamle |
| `greedy` | anlık puan artışını maksimize eder (hayvan + koridor + çoğunluk bonusu tahmini + doğa jetonu) |
| `heuristic` | greedy + en iyi adayları "geride bıraktığı fırsat değeri" ile yeniden sıralar (olasılık ağırlıklı, aşağıya bakın); işe yaramayan üçlü aşırı nüfusu siler |
| `lookahead` | en iyi `top_k` aday için `samples` determinize gelecek × `depth` tur greedy rollout (Monte Carlo) |
| `mcts` | determinizasyonlu, sıra-soyutlamalı açık döngü MCTS (aşağıya bakın) |

Parametreler spec ile verilir: `heuristic:potential_weight=0.5,top_k=16`,
`lookahead:top_k=8,samples=6,depth=2`, `mcts:iterations=300,depth=3` veya `mcts:time_limit=1.0`.

**Olasılık hesabı** (`cascadia_bot/bots/probability.py`): torbanın içeriği açık bilgiden kesin
hesaplanır (her türden 20 − tahtalarda/ortada/kenarda görünenler). Buradan, oyuncunun bir sonraki
turunda her hayvanın ortada bulunma olasılığı tahmin edilir (kalan 3 jeton + sıradaki çekilişler
havuzu, Poisson yaklaşımı). `heuristic` botunun fırsat değeri `potential_mode` ile seçilir:

| `potential_mode` | Fırsat değeri |
|---|---|
| `flat` | her hayvan için "bir jeton daha gelirse en iyi kazanç" toplamı (olasılıksız) |
| `prob` | aynı toplam, her terim o hayvanın gelme olasılığıyla çarpılır |
| `expmax` (varsayılan) | sıradaki turda gelecek hayvanlar arasından alınabilecek **en iyi** kazancın beklenen değeri (tek jeton alınabildiği için) |

Son turda fırsat değeri 0'dır. Ölçüm (`potential_weight=1`): solo 400 oyunda `expmax` 93.2 / `flat`
92.3 puan; 2 oyunculu kafa kafaya 400 oyunda `expmax` %56 kazandı.

**MCTS** (`cascadia_bot/bots/mcts.py`): her iterasyon gizli bilgiyi yeniden örnekler
(`game.determinize`). Kökte gerçek en iyi `top_k` aday, daha derinde ise "greedy sıralamasındaki
k'inci hamle" kenar olarak kullanılır (determinizasyonlar arasında somut hamleler değiştiği için).
Aşamalı genişletme ile ziyaret arttıkça daha fazla aday açılır; rakipler simülasyonda greedy oynar.
`depth` kendi turumuz kadar ilerledikten sonra pozisyon `puan + potential_weight × fırsat değeri`
ile değerlendirilir; ödül kendi değerimiz eksi en iyi rakibin değeri. Parametreler: `iterations`
(veya `time_limit` saniye), `top_k`, `depth`, `c` (UCB keşif sabiti, puan cinsinden),
`widen_c`, `widen_alpha`, `potential_weight`. Son hamlenin istatistikleri `bot.last_stats` içinde.

İlk ölçüm (varsayılanlar: 150 iterasyon, `top_k=8`, `depth=2`), rakip `heuristic`:

| Karşılaşma | Oyun | Ortalama puan (mcts / heuristic) | MCTS kazanma | Süre (s/oyun) |
|---|---|---|---|---|
| 2 oyuncu | 120 | 92.0 / 91.2 | %57.9 | 25.8 / 0.15 |
| solo | 60 | 93.4 / 92.9 | – | 11.8 / 0.18 |

**Çoğunluk bonusu tahmini** (`greedy`, `heuristic`, `lookahead` için ortak): her aday hamlede,
rakiplerin *şu anki* en büyük koridorlarına göre kendi bonusundaki değişim hesaplanır ve
`majority_weight × (tur / 20)` ile ağırlıklandırılır (rakipler henüz büyüyeceği için oyun başında
az, sonda tam). `majority_weight=0` bonusu tamamen yok sayar, `majority_ramp=false` ağırlığı
baştan tam verir.

Ölçümler (`majority_weight=1`, ramp açık, eski sürüm = `majority_weight=0`):

| Karşılaşma | Oyun | Ortalama puan (yeni / eski) | Yeninin kazanma oranı |
|---|---|---|---|
| greedy, 2 oyuncu | 600 | 88.2 / 86.6 | %57.3 |
| heuristic, 2 oyuncu | 400 | 91.4 / 90.6 | %53.8 |
| greedy, 4 oyuncu (eski, ağırlık 1, ağırlık 2, ramp'sız) | 200 | 87.9 / 87.9 | %30.8 (beklenen %25; ramp'sız %19) |
| greedy, solo | 400 | 88.0 / 87.8 | – |

**Rakibin bonusunu düşürme** (`majority_denial`, varsayılan 0): rakiplerden alınan bonus puanını da
değer olarak sayar; `denial_target=leader` yalnızca skorda öndeki rakibi, `mean` tüm rakiplerin
ortalamasını hesaba katar. Ölçümlerde anlamlı bir kazanç görülmedi, bu yüzden kapalı:

| Karşılaşma | Oyun | Kazanma oranı (denial / baz) |
|---|---|---|
| 2 oyuncu, denial=1 | 600 | %51.6 / %48.4 |
| 2 oyuncu, denial=0.5 | 600 | %52.2 / %47.8 |
| 4 oyuncu: leader=1 / leader=0.5 / mean=1 / baz | 400 | %28.0 / %23.6 / %23.5 / %24.9 |
| 3 oyuncu: leader=1 / mean=1 / baz | 399 | %29.1 / %34.2 / %36.7 |
