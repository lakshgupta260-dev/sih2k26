import re

with open('frontend/src/pages/project/Reports.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# I will find the exact start and end of the broken deleteMutation block
# and replace it cleanly.

new_mutation = '''
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
'''

# Find the start
start_idx = code.find('  const deleteMutation = useMutation({')
# Find the start of the next block which is requestMutation
end_idx = code.find('  const requestMutation = useMutation({')

code = code[:start_idx] + new_mutation + '\n' + code[end_idx:]

with open('frontend/src/pages/project/Reports.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
