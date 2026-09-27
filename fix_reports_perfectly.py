import re

with open('frontend/src/pages/project/Reports.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add Trash2 icon
code = code.replace('TrendingUp,', 'TrendingUp,\\n  Trash2,')

# 2. Add deleteMutation
delete_mutation = '''
  const deleteMutation = useMutation({
    mutationFn: (reportId: string) => generatedReportsApi.delete(projectId, reportId),
    onMutate: async (reportId: string) => {
      await queryClient.cancelQueries({ queryKey: ["generated-reports", projectId] });
      const previous = queryClient.getQueryData(["generated-reports", projectId]);
      queryClient.setQueryData(["generated-reports", projectId], (old: any) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.filter((r: any) => r.id !== reportId),
        };
      });
      return { previous };
    },
    onSuccess: () => {
      toast("Report deleted", "success");
    },
    onError: (err, reportId, context: any) => {
      queryClient.setQueryData(["generated-reports", projectId], context?.previous);
      if (err instanceof ApiError) {
        toast(err.message, "error");
      } else {
        toast("Failed to delete report", "error");
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["generated-reports", projectId] });
    },
  });

  const requestMutation = useMutation({
'''
code = code.replace('  const requestMutation = useMutation({', delete_mutation.strip())

# 3. Add DropdownItem
dropdown_item = '''
                        <DropdownSeparator />
                        <DropdownItem
                          icon={<Trash2 className="h-3.5 w-3.5 text-rose-500" />}
                          className="!text-rose-500 hover:!bg-rose-500/10"
                          onSelect={() => {
                            if (window.confirm("Are you sure you want to delete this report?")) {
                              deleteMutation.mutate(r.id);
                            }
                            close();
                          }}
                        >
                          Delete report
                        </DropdownItem>
'''
code = code.replace('                        <DropdownSeparator />\\n                        <DropdownItem\\n                          icon={<Copy className="h-3.5 w-3.5" />}', dropdown_item + '                        <DropdownItem\\n                          icon={<Copy className="h-3.5 w-3.5" />}')

with open('frontend/src/pages/project/Reports.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
