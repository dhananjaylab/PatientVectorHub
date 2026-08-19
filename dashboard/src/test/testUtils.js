import { jsx as _jsx } from "react/jsx-runtime";
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
export function createTestQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: 0 },
            mutations: { retry: false },
        },
    });
}
export function renderWithProviders(ui, { route = '/', queryClient = createTestQueryClient() } = {}) {
    function Wrapper({ children }) {
        return (_jsx(QueryClientProvider, { client: queryClient, children: _jsx(MemoryRouter, { initialEntries: [route], children: children }) }));
    }
    return { ...render(ui, { wrapper: Wrapper }), queryClient };
}
