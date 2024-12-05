import itertools

nested_list = [[1, 2, 3], [4, 5], [6, 7, 8, 9]]

flattened_list = list(itertools.chain(*nested_list))

print(flattened_list)  # [1, 2, 3, 4, 5, 6, 7, 8, 9]
