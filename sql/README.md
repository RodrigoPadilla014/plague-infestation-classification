# SQL Recipes

SQL recipes turn source tables into model-ready feature families.

Each recipe directory should own:

- the modeling grain;
- the target construction rule;
- feature-family SQL files;
- final dataset assembly;
- diagnostics that justify the recipe.

Current recipe:

```text
model1_january/
```

Dataset versions are outputs of a recipe, not separate SQL folders. A produced
dataset carries a manifest with the recipe name, SQL hashes, created timestamp,
and feature contract.
