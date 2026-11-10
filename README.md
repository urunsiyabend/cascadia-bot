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
  components.py    habitatlar, hayvanlar, 85 karo + 5 başlangıç karosu
  hexgrid.py       eksenel (q, r) hex koordinatları
  board.py         oyuncu ortamı: karo/jeton yerleştirme, koridorlar, hızlı "ya şöyle olsaydı" tablosu
  scoring.py       tüm puan kartları (A–D ×5, aile, orta seviye), çoğunluk, toplam
  game.py          oyun durumu ve tur akışı (aşırı nüfus, doğa jetonu, solo, oyun sonu, determinizasyon)
  runner.py        botlarla tek oyun oynatma
  arena.py         turnuva / CLI (koltuk rotasyonu, solo kıyas, paralel işlem, JSON çıktı)
  sweep.py         parametre taraması: aynı tohumlarla taban bota karşı puan farkı ± standart hata
  train_value.py   kendi kendine oyundan değer modeli eğitimi
  selfplay_stats.py aynı botla kendine karşı oyun: kazanan/kaybeden farkları, kart bazında puanlar
  render.py        metin tabanlı tahta çıktısı
  models/          eğitilmiş değer modelleri (value_{1,2,3,4}p.json)
  bots/
    simple.py        random, greedy, heuristic
    evaluation.py    hızlı aday değerlendirme, çoğunluk bonusu tahmini
    probability.py   torba içeriği, sıradaki tur olasılıkları, beklenen en iyi kazanç
    features.py      durum özellikleri + doğrusal değer modeli
    value.py         öğrenilmiş değerle tek adımlık bot
    lookahead.py     basit Monte Carlo ileri bakış
    mcts.py          determinizasyonlu açık döngü MCTS
    mce.py           düz Monte Carlo (en güçlü bot)
tests/             puan kartları, kurallar, hızlı yolların tam hesapla eşdeğerliği, botlar
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

## Botlar

| Bot | Fikir | Hız (2 oyuncu, sn/oyun) |
|---|---|---|
| `random` | rastgele yasal hamle | ~0 |
| `greedy` | anlık puan artışı: hayvan + koridor + çoğunluk bonusu tahmini + doğa jetonu | 0.03 |
| `heuristic` | greedy + en iyi adayları "sıradaki turda alınabilecek en iyi jetonun beklenen değeri" ile yeniden sıralar | 0.07 |
| `value` | greedy'nin en iyi 12 adayı için hamle sonrası durumun gerçek puanı + öğrenilmiş gelecek değeri | 0.14 |
| `lookahead` | basit Monte Carlo ileri bakış (eski, yerini `mce` aldı) | ~2–3 |
| `mcts` | determinizasyonlu, sıra-soyutlamalı açık döngü MCTS | ~10–15 |
| `mce` | **en güçlü**: düz Monte Carlo, 3 turluk simülasyon + öğrenilmiş değer, ardışık yarılama | ~10 |

Parametreler spec ile verilir, ör. `mce:horizon=5,playouts=96`, `mcts:depth=3`,
`heuristic:potential_mode=flat`, `greedy:majority_weight=0`. Gizli bilgiyle hile yapılmaz: simülasyon
yapan botlar `game.determinize(rng)` ile destenin sırasını ve torbayı yeniden örnekler.

## Sonuçlar (varsayılan ayarlar, rastgele A–D kartları)

**2 oyuncu**, aynı tohumlarla `heuristic`e karşı (oyun başına puan farkı ± standart hata):

| Bot | Oyun | Kazanma | Puan farkı | sn/oyun |
|---|---|---|---|---|
| `mce` | 160 | %79.7 | +5.47 ± 0.54 | 9.9 |
| `mcts:depth=3` | 160 | %63.7 | +2.66 ± 0.57 | 15.4 |
| `value` | 400 | %64.0 | +2.40 ± 0.38 | 0.14 |
| `mcts` (derinlik 2) | 160 | %54.7 | +0.20 ± 0.54 | 9.9 |
| `greedy` | 400 | %25.9 | −5.43 ± 0.42 | 0.03 |
| `random` | 400 | %0.0 | −62.12 ± 0.48 | ~0 |

**3 oyuncu** (99 oyun, koltuklar dönüşümlü; eşit güçte beklenen %33):

| Bot | Ortalama | Kazanma | sn/oyun |
|---|---|---|---|
| `mce` | 98.3 | %60.6 | 15.9 |
| `value` | 94.6 | %19.2 | 0.15 |
| `heuristic` | 93.6 | %20.2 | 0.07 |

**4 oyuncu** (100 oyun; beklenen %25):

| Bot | Ortalama | Kazanma | sn/oyun |
|---|---|---|---|
| `mce` | 97.8 | %53.0 | 22.5 |
| `value` | 95.0 | %30.0 | 0.17 |
| `heuristic` | 92.1 | %15.0 | 0.08 |
| `greedy` | 86.7 | %2.0 | 0.03 |

**Solo** (aynı 100 tohum; kural kitabı ölçeği: 90+ mükemmel, 100+ elit):

| Bot | Ortalama | sd | min–max | sn/oyun |
|---|---|---|---|---|
| `mce` | 98.7 | 5.5 | 87–117 | 4.9 |
| `value` | 93.7 | 6.0 | 75–106 | 0.13 |
| `heuristic` | 92.5 | 5.7 | 78–107 | 0.08 |
| `greedy` | 88.1 | 6.7 | 68–103 | 0.03 |

Tekrar üretmek için:

```bash
python -m cascadia_bot.sweep --baseline heuristic --games 160 --workers 4 --seed 10000 mce
python -m cascadia_bot.arena greedy heuristic value mce --solo --games 100 --workers 4 --seed 50000
python -m cascadia_bot.arena greedy heuristic value mce --games 100 --workers 4 --seed 60000
python -m cascadia_bot.arena heuristic value mce --games 99 --workers 4 --seed 70000
```

## Strateji analizi: MCE neden güçlü, MCE'ye karşı MCE'de ne kazandırıyor?

`python -m cascadia_bot.selfplay_stats <bot> --games 200 --workers 4` aynı botu iki koltukta oynatır;
kazanan − kaybeden farkını kategori bazında, kart bazında ortalama puanları ve davranışı (doğa jetonu,
silme, atılan jeton) raporlar.

**MCE'nin kazancı nereden geliyor?** Solo (aynı 100 tohum), MCE − heuristic: şahin **+4.7**, habitat
**+3.0**, doğa jetonu +0.8, ayı +0.6; geyik −2.0, tilki −0.7. 4 oyuncuda da aynı desen (şahin +4.5, habitat
+2.5). Şahin desenleri (birbirine komşu olmayan, görüş hattı olan şahinler) ve büyük koridorlar birkaç
tur sonra ödeme yapar: tek adımlık değerlendirme bunları göremez, gerçek çekilişleri örnekleyerek 3 tur
ileri bakan MCE görür. Avantajın büyük kısmı kendi ortamını daha iyi kurmaktan geliyor (solo +6.2), rakibi
engellemekten değil.

**Şahin avantajı karta bağlı.** Şahin kartı sabitlenerek (diğer kartlar rastgele, solo, kart başına 60
tohum) MCE − heuristic:

| Şahin kartı | Şahin puanı (mce / heuristic) | Şahin jetonu | Toplam fark |
|---|---|---|---|
| A (komşusuz şahinler) | 16.7 / 16.8 (−0.1 ± 0.7) | 5.6 / 5.6 | +5.3 ± 0.6 |
| B (komşusuz + görüş hattı) | 13.7 / 13.2 (+0.5 ± 1.1) | 4.2 / 4.1 | +5.5 ± 0.7 |
| C (görüş hattı başına 3) | **22.4 / 13.5 (+8.9 ± 1.5)** | 5.3 / 3.7 | +7.6 ± 0.9 |
| D (çift arasındaki türler) | 11.0 / 9.1 (+1.9 ± 0.9) | 3.1 / 2.6 | +5.8 ± 0.7 |

Şahin farkının neredeyse tamamı C kartından geliyor: orada her yeni şahin birden fazla görüş hattı açtığı
için değer birikerek artıyor ve MCE daha çok şahin koyuyor. A/B'de şahin farkı yok. Buna karşın MCE her şahin
kartında +5–8 puan önde; ortak kazanç habitat (+3.3 ± 0.25). MCE kart bazında yer değiştiriyor: geyik C/D'de
(−3.5 / −2.4) ve tilki C'de (−1.9) puandan vazgeçip habitat, şahin C/D, somon A ve ayı A'ya yatırıyor.

**MCE'ye karşı MCE (200 oyun), kazananı ne belirliyor?** Kazanan − kaybeden: toplam +5.8; hayvanlar
+4.1 (şahin +2.8 ± 0.9, somon +1.6 ± 0.6; ayı, geyik, tilki ≈ 0), habitat +0.6, çoğunluk bonusu +0.9.
Eşit güçteki botlar arasında oyunu en riskli/değişken desenler (şahin, somon koşuları) ve çoğunluk
bonusları belirliyor.

**Puan farkı mı, kendi puanı mı?** Varsayılan MCE ödülü "benim puanım − rakibin puanı". Yalnız kendi
puanına bakan sürüm (`mce:reward=own`) ile karşılaştırma:

| Ölçüm | `mce` (puan farkı) | `mce:reward=own` |
|---|---|---|
| Kafa kafaya (160 oyun) | – | −0.04 ± 0.52 puan, %47.5 → **eşit** |
| Kendine karşı ortalama puan | 92.8 | **97.5** |
| Karışık taslak için harcanan doğa jetonu (oyun başı) | 3.65 | 2.89 |
| heuristic'e karşı (aynı 160 tohum) | +5.47 ± 0.54, %79.7 | **+6.71 ± 0.57, %83.4** |
| sn/oyun | 9.9 | 8.2 |

Puan farkını hedeflemek, rakibin işine yarayacak çifti almaya ve doğa jetonu harcamaya iter; kazanma
şansını artırmaz, iki tarafın puanını da ~5 düşürür. 2 oyunculu ölçümlerde kendi ortamına odaklanmak en az
onun kadar iyi, daha yüksek puanlı ve daha hızlı. (3–4 oyuncu için bu karşılaştırma yapılmadı; varsayılan
şimdilik değiştirilmedi.)

**Daha çok hesaplama** (varsayılan MCE'ye karşı, 160 oyun): ufuk 5 +0.84 ± 0.57, 192 simülasyon
+0.95 ± 0.59 (ikisi de anlamlılık sınırında, 1.4–1.8× süre); aynı 96 simülasyonla 20 aday −1.39 ± 0.56
(aday başına simülasyon azalınca iyi adaylar gürültüyle eleniyor). Aday sayısı bütçeyle birlikte
artırılmalı.

## Algoritmalar ve deneyler

Tüm karşılaştırmalar `python -m cascadia_bot.sweep` ile yapıldı: aday bot, aynı tohumlarla (aynı kartlar,
aynı desteler) taban bota karşı 2 oyunculu oynar, koltuklar dönüşümlüdür. "Puan farkı" oyun başına aday −
taban puanı ± standart hatadır; kazanma oranından çok daha az gürültülü bir ölçüdür.

### 1. Çoğunluk bonusu tahmini (`greedy`, `heuristic`, `value`, simülasyonlar)

Her aday hamlede rakiplerin *şu anki* en büyük koridorlarına göre kendi bonus değişimi hesaplanır ve
`majority_weight × (tur / 20)` ile ağırlıklandırılır (rakipler henüz büyüyeceği için oyun başında az).

| Karşılaşma | Oyun | Ortalama puan (yeni / eski) | Yeninin kazanma oranı |
|---|---|---|---|
| greedy, 2 oyuncu | 600 | 88.2 / 86.6 | %57.3 |
| heuristic, 2 oyuncu | 400 | 91.4 / 90.6 | %53.8 |
| greedy, 4 oyuncu | 200 | 87.9 / 87.9 | %30.8 (beklenen %25; ağırlık baştan tam verilirse %19) |
| greedy, solo | 400 | 88.0 / 87.8 | – |

Rakibin bonusunu düşürmeyi ayrıca ödüllendirmek (`majority_denial`) anlamlı kazanç getirmedi
(2 oyuncu %51.6–52.2, 3–4 oyuncu baz ile aynı ya da kötü), bu yüzden kapalı.

### 2. Olasılık hesabı (`probability.py`)

Torbanın içeriği açık bilgiden kesin hesaplanır (her türden 20 − görünenler). Sıradaki turda her hayvanın
ortada olma olasılığı tahmin edilir. `heuristic` botunun fırsat değeri (`potential_mode`):
`flat` (olasılıksız toplam), `prob` (olasılık ağırlıklı toplam), `expmax` (varsayılan; tek jeton
alınabildiği için gelecek hayvanlar arasından **en iyi** kazancın beklenen değeri). Solo 400 oyunda
`expmax` 93.2 / `flat` 92.3; 2 oyunculu kafa kafaya 400 oyunda `expmax` %56.

### 3. MCTS (`mcts.py`)

Her iterasyon gizli bilgiyi yeniden örnekler. Kökte gerçek adaylar, derinde "greedy sıralamasındaki
k'inci hamle" kenar olarak kullanılır (somut hamleler determinizasyonlar arasında değiştiği için);
aşamalı genişletme, greedy rakipler, `depth` tur sonra değerlendirme.

| Ayar (taban: heuristic, 160 oyun) | Kazanma | Puan farkı | sn/oyun |
|---|---|---|---|
| derinlik 2, 150 iterasyon | %54.7 | +0.20 ± 0.54 | 9.9 |
| derinlik 3 | %63.7 | +2.66 ± 0.57 | 15.4 |

### 4. Düz Monte Carlo — MCE (`mce.py`)

Kingdomino çalışmasında (Gedda vd., 2018) düz Monte Carlo UCT'yi geçmişti. Her aday için gizli bilgi
yeniden örneklenir, hamle oynanır, herkes `horizon` tur greedy oynar, pozisyon değerlendirilir; bütçe
ardışık yarılama ile dağıtılır (her turda kötü yarı elenir).

**Oyun sonuna kadar simülasyon işe yaramadı.** İki iyi aday arasındaki fark tek simülasyonda oyun sonunda
~7–10 puan gürültü içinde kalıyor (1–2 tur ufukta ~2 puan); adaylar arasındaki gerçek fark ise 1–5 puan.
Farklı ilk hamleden sonra kararlar kaotik biçimde ayrıştığı için ortak rastgele sayılar ve sabit torba
sırası bu gürültüyü azaltmadı. Kısa ufuk + iyi değerlendirme çözüm oldu:

| Ayar (taban: heuristic, 160 oyun) | Kazanma | Puan farkı | sn/oyun |
|---|---|---|---|
| oyun sonu, 24 / 48 simülasyon | %34.1 / %41.6 | −2.49 / −0.72 | 9 / 18 |
| ufuk 2, 96 sim. | %60.3 | +1.43 ± 0.63 | 6.3 |
| ufuk 3, 96 sim. | %71.2 | +3.87 ± 0.58 | 9.2 |
| ufuk 3, 192 sim. | %73.1 | +4.79 ± 0.60 | 19.0 |
| ufuk 4, 96 sim. | %74.4 | +4.61 ± 0.60 | 11.6 |
| ufuk 5, 96 sim. | %76.6 | +4.79 ± 0.59 | 13.5 |
| ufuk 5, 96 sim., 12 aday | %81.2 | +5.53 ± 0.50 | 15.4 |
| ufuk 8, 96 sim. | %70.6 | +3.89 ± 0.62 | 23.0 |
| ufuk 2, 12 aday, **öğrenilmiş değer** | %70.3 | +4.88 ± 0.64 | 7.1 |
| **ufuk 3, 12 aday, öğrenilmiş değer (varsayılan)** | %75.0 | **+5.85 ± 0.64** | 10.2 |
| ufuk 5, 12 aday, öğrenilmiş değer | %75.9 | +5.52 ± 0.63 | 15.8 |

Aynı süre bütçesinde ağaçsız MCE, ağaçlı MCTS'i açık farkla geçiyor (+5.5 / +2.7): bu oyunda
belirleyici olan ağaç değil, doğru ufuk, aday genişliği ve değerlendirme kalitesi.

### Doğa jetonuyla jeton silme (`wipes.py`, `nature_wipes=true`, varsayılan kapalı)

Silinecek ortadaki jetonlar için yerine gelecekler torbanın açık içeriğinden örneklenir; beklenen en iyi
hamle değeri, harcanan jetonun 1 puanını ve bir eşiği aşarsa silinir. Seçilen silme bağımsız örneklerle
yeniden doğrulanır ("kazananın laneti": birkaç gürültülü tahminin en büyüğü fazla iyimserdir).

| Ayar (aynı tohumlarla silmesiz sürüme karşı, 400 oyun) | Puan farkı |
|---|---|
| heuristic, 8 örnek, doğrulamasız | −1.07 ± 0.40 |
| heuristic, 8 örnek, doğrulamalı | −0.81 ± 0.40 |
| heuristic, 24 örnek | +0.01 ± 0.37 |
| heuristic, 24 örnek, eşik 1 | +0.32 ± 0.39 |
| value, 24 örnek | −0.41 ± 0.35 |
| heuristic solo, 300 oyun | 92.0 / 92.7 (silmesiz) |

Sonuç: bu değerlendirmeyle silme en iyi ihtimalle nötr. Ortada 4 çift ve doğa jetonuyla karışık seçim
zaten yeterli esneklik sağlıyor; harcanan jeton ise kesin 1 puan.

### 5. Öğrenilmiş değer fonksiyonu (`features.py`, `train_value.py`)

Bir oyuncunun **kalan puanını** (oyun sonu puanı − şu anki puan) tahmin eden doğrusal model.
Özellikler: kalan tur, doğa jetonu, her habitat için en büyük koridorun açık kenarları ve rakiplerle
farkı, her hayvan için (puan kartına göre ayrı ağırlıkla) jeton sayısı, açık yer sayısı, bir jeton daha
gelirse en iyi kazanç, torba oranı ve sıradaki tur olasılığı. Kendi kendine oyunlardan ridge regresyonla
eğitilir; politika iterasyonu: önce `heuristic`/`greedy` oyunları, sonra modeli kullanan `value` botunun
oyunları.

```bash
python -m cascadia_bot.train_value --players 2 --games 6000 --workers 4 --policy value value heuristic
```

| Model (2 oyuncu) | Test hatası (yalnız zaman / model) | value botu, heuristic'e karşı |
|---|---|---|
| v1 (heuristic+greedy oyunları, 4000) | 5.37 / 4.76 puan | %61.8, +1.81 ± 0.38 (400 oyun) |
| v2 (value oyunları, 6000) — **varsayılan** | 4.99 / 4.15 puan | %64.0, +2.40 ± 0.38 (400 oyun) |
| v3 (v2 ile value oyunları) | 4.96 / 4.16 puan | v2'ye karşı −0.03 ± 0.25 → doygun |

v2, v1'i kafa kafaya 800 oyunda +0.67 ± 0.27 puan farkla yendi. 1, 3 ve 4 oyuncu için de iki
iterasyonla eğitilmiş modeller `models/` altında.

## Kaynaklar

- Resmi kural kitabı (AEG / Flatout Games) ve tasarımcının BGG / FAQ açıklamaları
- Gedda, Lagerkvist, Butler — [Monte Carlo Methods for the Game Kingdomino](https://arxiv.org/abs/1807.04458) (2018)
- Cowling, Powley, Whitehouse — Information Set Monte Carlo Tree Search (2012)
- Szubert, Jaśkowski — Temporal Difference Learning of N-Tuple Networks for the Game 2048 (2014)
- Couëtoux vd. — Continuous Upper Confidence Trees / progressive widening (2011)
- Karo verisi [davidxmoody/cascadia-ai](https://github.com/davidxmoody/cascadia-ai) ile çapraz kontrol edildi
