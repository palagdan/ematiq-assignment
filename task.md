# Full-stack úloha pro kandidáty

Skupina kolegů z práce pravidelně chodí na oběd do blízkých restaurací. Navrhněte webovou aplikaci, která umožní těmto kolegům si o obědy zahrát.

Kdo prohraje, platí obědy všem zúčastněným.

### Požadavky:

- Při hře musí každý hráč provést interakci s aplikací.
    
    *Např.: zvolení pole v ruletě,...*
    
- Hráčům, kteří jsou připojení ve stejné místnosti¹, se aktualizuje stránka po akcích ostatních hráčů
- Stav aplikace musí zůstat zachován po refreshi stránky
- Hráč musí mít možnost zobrazit historii všech odehraných her s informacemi:
    - kdo hrál, jak drahé bylo jejich jídlo a v jaké měně (Kč, €, ₿)
    - kdo vyhrál
    - kdy se tak stalo
1. Místnost je specifický virtuální prostor, ve kterém spolu mohou hráči hrát. Má zabránit interakci mezi hráči, kteří spolu nehrají

### Frontend požadavky:

- Web App (Client Only)
- TypeScript 5+
- React 18+
- Chrome 120+

### Backend požadavky:

- Python 3.12+
- Asyncio
- Mypy
- Fastapi

### Dodatečné informace:

- Zdroj měnových kurzů si můžete mockovat jako samostatnou službu, nebo použít jakékoliv veřejně dostupné API.

### Způsob odevzdání

- Veřejně dostupný git repozitář po celou dobu hiringu.